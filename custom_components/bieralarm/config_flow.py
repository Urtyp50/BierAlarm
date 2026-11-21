"""Config and options flow for BierAlarm."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    BILLA_REGIONS,
    CONF_AI_TASK_ENTITY,
    CONF_BILLA_REGION,
    CONF_EXTRA_LEAFLETS,
    CONF_FAVORITE_BRANDS,
    CONF_LIDL_REGION,
    CONF_MAX_PRICE_PER_LITER,
    CONF_NOTIFY_ENTITY,
    CONF_RADIUS_KM,
    CONF_STORES,
    DEFAULT_BILLA_REGION,
    DEFAULT_LIDL_REGION,
    DEFAULT_STORES,
    DOMAIN,
    LIDL_REGIONS,
    STORE_NAMES,
)


def _schema(values: dict[str, Any]) -> vol.Schema:
    def default(key: str, fallback: Any = None) -> dict:
        value = values.get(key, fallback)
        return {"default": value} if value not in (None, "") else {}

    return vol.Schema(
        {
            vol.Required(CONF_STORES, **default(CONF_STORES, DEFAULT_STORES)): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=k, label=v) for k, v in STORE_NAMES.items()],
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Required(
                CONF_LIDL_REGION, **default(CONF_LIDL_REGION, DEFAULT_LIDL_REGION)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[selector.SelectOptionDict(value=k, label=v) for k, v in LIDL_REGIONS.items()],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(
                CONF_BILLA_REGION, **default(CONF_BILLA_REGION, DEFAULT_BILLA_REGION)
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(options=BILLA_REGIONS, mode=selector.SelectSelectorMode.DROPDOWN)
            ),
            vol.Optional(CONF_RADIUS_KM, **default(CONF_RADIUS_KM)): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=100, step=1, unit_of_measurement="km", mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_AI_TASK_ENTITY, **default(CONF_AI_TASK_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="ai_task")
            ),
            vol.Optional(CONF_FAVORITE_BRANDS, **default(CONF_FAVORITE_BRANDS)): selector.TextSelector(),
            vol.Optional(
                CONF_MAX_PRICE_PER_LITER, **default(CONF_MAX_PRICE_PER_LITER)
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=20, step=0.05, unit_of_measurement="€/l", mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Optional(CONF_NOTIFY_ENTITY, **default(CONF_NOTIFY_ENTITY)): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="notify")
            ),
            vol.Optional(CONF_EXTRA_LEAFLETS, **default(CONF_EXTRA_LEAFLETS)): selector.TextSelector(
                selector.TextSelectorConfig(multiline=True)
            ),
        }
    )


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not user_input.get(CONF_STORES) and not user_input.get(CONF_EXTRA_LEAFLETS):
        errors[CONF_STORES] = "no_stores"
    return errors


class BierAlarmConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(title="BierAlarm", data={}, options=user_input)
        return self.async_show_form(
            step_id="user", data_schema=_schema(user_input or {}), errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return BierAlarmOptionsFlow()


class BierAlarmOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(data=user_input)
        values = user_input or dict(self.config_entry.options)
        return self.async_show_form(step_id="init", data_schema=_schema(values), errors=errors)
