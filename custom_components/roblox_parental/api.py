from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import (
    URL_AUTHENTICATED,
    URL_BLOCKED_EXPERIENCES,
    URL_CHILD_SETTINGS,
    URL_CHILDREN_INFO,
    URL_GAMES,
    URL_PRESENCE,
    URL_TOP_UNIVERSES,
    URL_WEEKLY_SCREENTIME,
    USER_AGENT,
)

_LOGGER = logging.getLogger(__name__)


class RobloxAuthError(Exception):
    pass


class RobloxRateLimitError(Exception):
    pass


class RobloxApiError(Exception):
    pass


class RobloxParentalClient:
    def __init__(self, cookie: str, name_cache: dict[int, str] | None = None) -> None:
        self._cookie = cookie
        self._csrf_token: str | None = None
        self._name_cache: dict[int, str] = name_cache or {}
        self._session: aiohttp.ClientSession | None = None

    def _make_session(self) -> aiohttp.ClientSession:
        return aiohttp.ClientSession(
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json",
            },
            cookies={".ROBLOSECURITY": self._cookie},
        )

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = self._make_session()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, url: str, params: dict | None = None) -> Any:
        session = await self._get_session()
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 401:
                    raise RobloxAuthError("Cookie invalid or expired (401)")
                if resp.status == 403:
                    raise RobloxAuthError("Forbidden (403) on GET — cookie may be invalid")
                if resp.status == 429:
                    raise RobloxRateLimitError("Rate limited (429)")
                if resp.status >= 500:
                    raise RobloxApiError(f"Server error {resp.status}")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise RobloxApiError(f"Network error: {err}") from err

    async def _post(self, url: str, json: dict) -> Any:
        session = await self._get_session()

        async def _do_post() -> aiohttp.ClientResponse:
            headers: dict[str, str] = {}
            if self._csrf_token:
                headers["x-csrf-token"] = self._csrf_token
            return session.post(url, json=json, headers=headers)

        try:
            async with await _do_post() as resp:
                if resp.status == 403:
                    new_csrf = resp.headers.get("x-csrf-token")
                    if new_csrf:
                        self._csrf_token = new_csrf
                        async with await _do_post() as retry:
                            if retry.status == 401:
                                raise RobloxAuthError("Cookie invalid or expired (401 on retry)")
                            if retry.status == 403:
                                raise RobloxAuthError("Forbidden (403) after csrf retry")
                            if retry.status == 429:
                                raise RobloxRateLimitError("Rate limited (429)")
                            if retry.status >= 500:
                                raise RobloxApiError(f"Server error {retry.status}")
                            retry.raise_for_status()
                            return await retry.json(content_type=None)
                    raise RobloxAuthError("Forbidden (403) — no csrf token in response")
                if resp.status == 401:
                    raise RobloxAuthError("Cookie invalid or expired (401)")
                if resp.status == 429:
                    raise RobloxRateLimitError("Rate limited (429)")
                if resp.status >= 500:
                    raise RobloxApiError(f"Server error {resp.status}")
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise RobloxApiError(f"Network error: {err}") from err

    async def authenticate(self) -> dict:
        return await self._get(URL_AUTHENTICATED)

    async def get_children(self) -> list[dict]:
        data = await self._get(URL_CHILDREN_INFO)
        return data.get("childrenInfoList", [])

    async def get_weekly_screentime(self, child_id: int) -> list[dict]:
        data = await self._get(URL_WEEKLY_SCREENTIME, params={"userId": child_id})
        return data.get("dailyScreentimes", [])

    async def get_top_universes(self, child_id: int) -> list[dict]:
        data = await self._get(URL_TOP_UNIVERSES, params={"userId": child_id})
        return data.get("universeWeeklyScreentimes", [])

    async def get_blocked(self, child_id: int) -> set[int]:
        data = await self._post(
            URL_BLOCKED_EXPERIENCES,
            {"targetUserId": child_id, "limit": 50, "offset": 0},
        )
        entries = data.get("blockedExperiences", data.get("experiences", []))
        return {int(e["universeId"]) for e in entries if "universeId" in e}

    async def get_child_settings(self, child_id: int) -> dict:
        return await self._get(URL_CHILD_SETTINGS, params={"childUserId": child_id})

    async def resolve_names(self, universe_ids: list[int]) -> dict[int, str]:
        to_fetch = [uid for uid in universe_ids if uid not in self._name_cache]
        if to_fetch:
            chunk_size = 50
            for i in range(0, len(to_fetch), chunk_size):
                chunk = to_fetch[i : i + chunk_size]
                try:
                    data = await self._get(URL_GAMES, params={"universeIds": ",".join(str(u) for u in chunk)})
                    for game in data.get("data", []):
                        uid = int(game["id"])
                        self._name_cache[uid] = game.get("name", str(uid))
                except RobloxApiError as err:
                    _LOGGER.warning("Failed to resolve game names for chunk: %s", err)
        return {uid: self._name_cache.get(uid, str(uid)) for uid in universe_ids}

    async def get_presence(self, child_id: int) -> dict:
        data = await self._post(URL_PRESENCE, {"userIds": [child_id]})
        users = data.get("userPresences", [])
        if users:
            return users[0]
        return {}

    @property
    def name_cache(self) -> dict[int, str]:
        return dict(self._name_cache)
