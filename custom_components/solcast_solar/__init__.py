"""Support for Solcast PV forecast."""

import logging
import traceback

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client
from homeassistant.helpers.device_registry import async_get as device_registry

from .const import DOMAIN, SOLCAST_URL, CONST_DISABLEAUTOPOLL, CONST_AVAILABLEAPIREQUESTS, SERVICE_UPDATE, SERVICE_CLEAR_DATA
from .coordinator import SolcastUpdateCoordinator
from .solcastapi import ConnectionOptions, SolcastApi

PLATFORMS = ["sensor"]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up solcast parameters."""

    try:

        options = ConnectionOptions(
            entry.options[CONF_API_KEY],
            SOLCAST_URL,
            hass.config.path('solcast.json')
        )

        solcast = SolcastApi(aiohttp_client.async_get_clientsession(hass), options)
        await solcast.sites_data()
        await solcast.load_saved_data()
        availableapirequests = entry.options[CONST_AVAILABLEAPIREQUESTS]
        coordinator = SolcastUpdateCoordinator(hass, solcast, availableapirequests)
        autopolldisabled = entry.options[CONST_DISABLEAUTOPOLL]
        await coordinator.setup(autopolldisabled, availableapirequests)

        await coordinator.async_config_entry_first_refresh()
        #await _async_migrate_unique_ids(hass, entry, coordinator)

        entry.async_on_unload(entry.add_update_listener(async_update_options))

        hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
        

        #hass.config_entries.async_setup_platforms(entry, PLATFORMS)
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        async def handle_service_update_forecast(call):
            """Handle service call"""
            _LOGGER.debug("executing update_forecasts service call")
            #await solcast.force_api_poll(True)
            await coordinator.service_event_update()

        async def handle_service_clear_solcast_data(call):
            """Handle service call"""
            _LOGGER.debug("Deleting the old solcast.json file to clear old solcast data")
            await coordinator.service_event_delete_old_solcast_json_file()

        hass.services.async_register(
            DOMAIN, SERVICE_UPDATE, handle_service_update_forecast
        )
        hass.services.async_register(
            DOMAIN, SERVICE_CLEAR_DATA, handle_service_clear_solcast_data
        )

        #hass.bus.async_listen("solcast_update_all_forecasts", coordinator.service_event_update)

        return True

    except Exception as err:
        _LOGGER.error("async_setup_entry: %s",traceback.format_exc())
        return False

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    hass.services.async_remove(DOMAIN, SERVICE_UPDATE)
    hass.services.async_remove(DOMAIN, SERVICE_CLEAR_DATA)

    return unload_ok

async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry, device) -> bool:
    device_registry(hass).async_remove_device(device.id)
    return True

async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    try:
        coordinator: SolcastUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        if coordinator._auto_fetch_tracker:
            #_LOGGER.debug("async_remove_entry removed auto fetch timer")
            coordinator._auto_fetch_tracker()
            coordinator._auto_fetch_tracker = None

    except Exception as err:
        _LOGGER.error("async_remove_entry: %s",traceback.format_exc())

async def async_update_options(hass: HomeAssistant, entry: ConfigEntry):
    """Reload entry if options change."""
    _LOGGER.debug("Reloading entry %s", entry.entry_id)
    if not entry.options[CONST_DISABLEAUTOPOLL]:
        coordinator: SolcastUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
        if coordinator._auto_fetch_tracker:
            _LOGGER.debug("** THERE IS A AUTO FETCHER!!")

    await hass.config_entries.async_reload(entry.entry_id)

async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""
    try:
        _LOGGER.debug("Solcast Config Migrating from version %s", config_entry.version)

        if config_entry.version == 2:
            #new_data = {**config_entry.options}
            new_data = {**config_entry.options, CONST_DISABLEAUTOPOLL: False}

            config_entry.version = 3
            hass.config_entries.async_update_entry(config_entry, options=new_data)

        _LOGGER.info("Solcast Config Migration to version %s successful", config_entry.version)
        return True
    except Exception as err:
        _LOGGER.error("Solcast - async_migrate_entry error: %s",traceback.format_exc())
        return False