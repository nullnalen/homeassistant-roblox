from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import RobloxAuthError, RobloxParentalClient
from .const import (
    CONF_CHILD_IDS,
    CONF_COOKIE,
    CONF_FAST_INTERVAL,
    CONF_PRESENCE_ENABLED,
    CONF_SLOW_INTERVAL,
    DEFAULT_FAST_POLL_INTERVAL,
    DEFAULT_SLOW_POLL_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class RobloxParentalConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._cookie: str = ""
        self._children: list[dict] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            client = RobloxParentalClient(cookie)
            try:
                me = await client.authenticate()
                self._cookie = cookie
                self._children = await client.get_children()
            except RobloxAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during authentication")
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                if not self._children:
                    errors["base"] = "no_children"
                else:
                    return await self.async_step_select_children()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COOKIE): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_select_children(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_ids = user_input[CONF_CHILD_IDS]
            if not selected_ids:
                errors["base"] = "no_children_selected"
            else:
                child_ids = [int(cid) for cid in selected_ids]
                selected_names = [
                    c.get("displayName", c.get("name", str(c["userId"])))
                    for c in self._children
                    if str(c["userId"]) in selected_ids
                ]
                title = ", ".join(selected_names)
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_COOKIE: self._cookie,
                        CONF_CHILD_IDS: child_ids,
                    },
                )

        options = [
            SelectOptionDict(
                value=str(c["userId"]),
                label=c.get("displayName", c.get("name", str(c["userId"]))),
            )
            for c in self._children
        ]

        return self.async_show_form(
            step_id="select_children",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CHILD_IDS): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            cookie = user_input[CONF_COOKIE].strip()
            client = RobloxParentalClient(cookie)
            try:
                await client.authenticate()
            except RobloxAuthError:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "cannot_connect"
            finally:
                await client.close()

            if not errors:
                entry = self._get_reauth_entry()
                self.hass.config_entries.async_update_entry(
                    entry,
                    data={**entry.data, CONF_COOKIE: cookie},
                )
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_COOKIE): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"domain": DOMAIN},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RobloxParentalOptionsFlow:
        return RobloxParentalOptionsFlow()


class RobloxParentalOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            new_cookie = user_input.pop(CONF_COOKIE, "").strip()
            if new_cookie:
                client = RobloxParentalClient(new_cookie)
                try:
                    await client.authenticate()
                except RobloxAuthError:
                    errors[CONF_COOKIE] = "invalid_auth"
                except Exception:
                    errors[CONF_COOKIE] = "cannot_connect"
                finally:
                    await client.close()

                if not errors:
                    self.hass.config_entries.async_update_entry(
                        self.config_entry,
                        data={**self.config_entry.data, CONF_COOKIE: new_cookie},
                    )

            if not errors:
                return self.async_create_entry(data=user_input)

        current = self.config_entry.options

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_COOKIE, default=""): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                    vol.Optional(
                        CONF_SLOW_INTERVAL,
                        default=current.get(CONF_SLOW_INTERVAL, DEFAULT_SLOW_POLL_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(min=10, max=120, step=5, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_FAST_INTERVAL,
                        default=current.get(CONF_FAST_INTERVAL, DEFAULT_FAST_POLL_INTERVAL),
                    ): NumberSelector(
                        NumberSelectorConfig(min=1, max=10, step=1, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Optional(
                        CONF_PRESENCE_ENABLED,
                        default=current.get(CONF_PRESENCE_ENABLED, True),
                    ): bool,
                }
            ),
            errors=errors,
        )
