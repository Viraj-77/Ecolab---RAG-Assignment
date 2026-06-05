from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

import requests


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# USGS TOOL SCHEMA
# ---------------------------------------------------------------------
USGS_TOOL = {
    "type": "function",
    "function": {
        "name": "get_water_quality",
        "description": (
            "Fetch recent/live water quality measurements from the public USGS "
            "Instantaneous Values Service for a US state. Use this tool only when "
            "the user asks for current, recent, latest, live, or location-specific "
            "water quality readings. Do not use it for general document-only RAG questions."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "state_fips": {
                    "type": "string",
                    "description": (
                        "Optional two-digit US state FIPS code. "
                        "Examples: Minnesota=27, Texas=48, California=06, Florida=12, New York=36."
                    ),
                },
                "state_name": {
                    "type": "string",
                    "description": (
                        "Optional US state name or abbreviation. "
                        "Examples: Minnesota, MN, Texas, TX, California, CA."
                    ),
                },
                "parameter": {
                    "type": "string",
                    "description": (
                        "Water quality parameter. Examples: pH, nitrate, temperature, "
                        "dissolved oxygen, conductance, turbidity."
                    ),
                },
                "period_days": {
                    "type": "integer",
                    "description": (
                        "Number of recent days to search. Default is 7. "
                        "Use 1 for last 24 hours, 7 for last week."
                    ),
                },
            },
            "required": [],
        },
    },
}


ALL_TOOLS = [USGS_TOOL]


# ---------------------------------------------------------------------
# USGS API CONFIG
# ---------------------------------------------------------------------
USGS_ENDPOINT = "https://waterservices.usgs.gov/nwis/iv/"

REQUEST_TIMEOUT_SECONDS = 30
MAX_RECORDS = 5
DEFAULT_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 30


PARAM_CODES = {
    "ph": "00400",
    "p h": "00400",
    "temperature": "00010",
    "temp": "00010",
    "water temperature": "00010",
    "nitrate": "00630",
    "nitrate plus nitrite": "00631",
    "dissolved oxygen": "00300",
    "oxygen": "00300",
    "do": "00300",
    "conductance": "00095",
    "specific conductance": "00095",
    "turbidity": "63680",
}


STATE_FIPS = {
    "alabama": "01",
    "alaska": "02",
    "arizona": "04",
    "arkansas": "05",
    "california": "06",
    "colorado": "08",
    "connecticut": "09",
    "delaware": "10",
    "florida": "12",
    "georgia": "13",
    "hawaii": "15",
    "idaho": "16",
    "illinois": "17",
    "indiana": "18",
    "iowa": "19",
    "kansas": "20",
    "kentucky": "21",
    "louisiana": "22",
    "maine": "23",
    "maryland": "24",
    "massachusetts": "25",
    "michigan": "26",
    "minnesota": "27",
    "mississippi": "28",
    "missouri": "29",
    "montana": "30",
    "nebraska": "31",
    "nevada": "32",
    "new hampshire": "33",
    "new jersey": "34",
    "new mexico": "35",
    "new york": "36",
    "north carolina": "37",
    "north dakota": "38",
    "ohio": "39",
    "oklahoma": "40",
    "oregon": "41",
    "pennsylvania": "42",
    "rhode island": "44",
    "south carolina": "45",
    "south dakota": "46",
    "tennessee": "47",
    "texas": "48",
    "utah": "49",
    "vermont": "50",
    "virginia": "51",
    "washington": "53",
    "west virginia": "54",
    "wisconsin": "55",
    "wyoming": "56",
}


STATE_ABBREVIATIONS = {
    "al": "alabama",
    "ak": "alaska",
    "az": "arizona",
    "ar": "arkansas",
    "ca": "california",
    "co": "colorado",
    "ct": "connecticut",
    "de": "delaware",
    "fl": "florida",
    "ga": "georgia",
    "hi": "hawaii",
    "id": "idaho",
    "il": "illinois",
    "in": "indiana",
    "ia": "iowa",
    "ks": "kansas",
    "ky": "kentucky",
    "la": "louisiana",
    "me": "maine",
    "md": "maryland",
    "ma": "massachusetts",
    "mi": "michigan",
    "mn": "minnesota",
    "ms": "mississippi",
    "mo": "missouri",
    "mt": "montana",
    "ne": "nebraska",
    "nv": "nevada",
    "nh": "new hampshire",
    "nj": "new jersey",
    "nm": "new mexico",
    "ny": "new york",
    "nc": "north carolina",
    "nd": "north dakota",
    "oh": "ohio",
    "ok": "oklahoma",
    "or": "oregon",
    "pa": "pennsylvania",
    "ri": "rhode island",
    "sc": "south carolina",
    "sd": "south dakota",
    "tn": "tennessee",
    "tx": "texas",
    "ut": "utah",
    "vt": "vermont",
    "va": "virginia",
    "wa": "washington",
    "wv": "west virginia",
    "wi": "wisconsin",
    "wy": "wyoming",
}


# ---------------------------------------------------------------------
# JSON / ARGUMENT HELPERS
# ---------------------------------------------------------------------
def _json_response(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _parse_arguments(arguments: str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments

    if isinstance(arguments, str):
        try:
            parsed = json.loads(arguments)
            if isinstance(parsed, dict):
                return parsed

            return {
                "error": "Tool arguments JSON must be an object.",
                "raw": arguments,
            }

        except json.JSONDecodeError:
            return {
                "error": "Could not parse tool arguments as JSON.",
                "raw": arguments,
            }

    return {
        "error": f"Unsupported tool argument type: {type(arguments).__name__}",
        "raw": str(arguments),
    }


def _normalize_state_name(state_name: str | None) -> str | None:
    if not state_name:
        return None

    cleaned = str(state_name).strip().lower()

    if not cleaned:
        return None

    if cleaned in STATE_ABBREVIATIONS:
        return STATE_ABBREVIATIONS[cleaned]

    return cleaned


def _resolve_state_fips(
    state_fips: str | None = None,
    state_name: str | None = None,
) -> str | None:
    if state_fips:
        cleaned = str(state_fips).strip()

        if cleaned.isdigit() and len(cleaned) in {1, 2}:
            return cleaned.zfill(2)

    normalized_state = _normalize_state_name(state_name)

    if normalized_state:
        return STATE_FIPS.get(normalized_state)

    return None


def _resolve_parameter_code(parameter: str | None = None) -> tuple[str, str]:
    parameter_name = (parameter or "pH").strip()
    parameter_key = parameter_name.lower()

    return parameter_name, PARAM_CODES.get(parameter_key, "00400")


def _resolve_period_days(period_days: Any = None) -> int:
    try:
        days = int(period_days) if period_days is not None else DEFAULT_PERIOD_DAYS
    except (TypeError, ValueError):
        days = DEFAULT_PERIOD_DAYS

    if days < 1:
        return 1

    if days > MAX_PERIOD_DAYS:
        return MAX_PERIOD_DAYS

    return days


def _safe_get_site_code(source_info: dict[str, Any]) -> str:
    site_codes = source_info.get("siteCode", [])

    if isinstance(site_codes, list) and site_codes:
        return str(site_codes[0].get("value", ""))

    return ""


def _parse_datetime(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def _latest_reading(readings: list[dict[str, Any]]) -> dict[str, Any]:
    if not readings:
        return {}

    return max(
        readings,
        key=lambda item: _parse_datetime(str(item.get("dateTime", ""))),
    )


def _extract_latest_records(
    sites: list[dict[str, Any]],
    max_records: int = MAX_RECORDS,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    for site in sites[:max_records]:
        source_info = site.get("sourceInfo", {})
        variable = site.get("variable", {})
        values = site.get("values", [])

        readings = []
        if values and isinstance(values, list):
            readings = values[0].get("value", []) or []

        latest = _latest_reading(readings)

        records.append(
            {
                "site_name": source_info.get("siteName", "Unknown site"),
                "site_code": _safe_get_site_code(source_info),
                "value": latest.get("value", "N/A"),
                "unit": variable.get("unit", {}).get("unitCode", ""),
                "time": latest.get("dateTime", ""),
                "variable": variable.get("variableName", ""),
                "qualifiers": latest.get("qualifiers", []),
                "latitude": source_info.get("geoLocation", {})
                .get("geogLocation", {})
                .get("latitude", ""),
                "longitude": source_info.get("geoLocation", {})
                .get("geogLocation", {})
                .get("longitude", ""),
            }
        )

    return records


# ---------------------------------------------------------------------
# PUBLIC TOOL EXECUTION
# ---------------------------------------------------------------------
def execute_tool(name: str, arguments: str | dict[str, Any]) -> str:
    """
    Execute registered tool by name.

    Returns JSON string because OpenAI tool messages expect text content.
    """
    args = _parse_arguments(arguments)

    if "error" in args:
        return _json_response(args)

    if name == "get_water_quality":
        return _fetch_water_quality(
            state_fips=args.get("state_fips"),
            state_name=args.get("state_name"),
            parameter=args.get("parameter", "pH"),
            period_days=args.get("period_days", DEFAULT_PERIOD_DAYS),
        )

    return _json_response(
        {
            "error": f"No tool registered with name: {name}",
            "available_tools": ["get_water_quality"],
        }
    )


def _fetch_water_quality(
    state_fips: str | None = None,
    state_name: str | None = None,
    parameter: str | None = "pH",
    period_days: int | None = DEFAULT_PERIOD_DAYS,
) -> str:
    """
    Fetch recent water-quality data from the public USGS Instantaneous Values API.

    This API is US-only because it uses USGS NWIS monitoring stations.
    """
    resolved_state_fips = _resolve_state_fips(
        state_fips=state_fips,
        state_name=state_name,
    )

    if not resolved_state_fips:
        return _json_response(
            {
                "error": "Could not resolve US state FIPS code.",
                "state_fips": state_fips,
                "state_name": state_name,
                "hint": (
                    "Provide a US state name like Minnesota, Texas, California, "
                    "or a FIPS code like 27."
                ),
            }
        )

    parameter_name, parameter_code = _resolve_parameter_code(parameter)
    days = _resolve_period_days(period_days)

    verify_ssl = os.getenv("USGS_VERIFY_SSL", "true").lower() != "false"

    params = {
        "format": "json",
        "stateCd": resolved_state_fips,
        "parameterCd": parameter_code,
        "siteStatus": "active",
        "period": f"P{days}D",
    }

    headers = {
        "Accept": "application/json",
        "User-Agent": "Ecolab-RAG-Assignment/1.0",
    }

    try:
        logger.info(
            "Calling USGS API | endpoint=%s | state_fips=%s | parameter=%s | code=%s | period=P%sD",
            USGS_ENDPOINT,
            resolved_state_fips,
            parameter_name,
            parameter_code,
            days,
        )

        response = requests.get(
            USGS_ENDPOINT,
            params=params,
            headers=headers,
            timeout=REQUEST_TIMEOUT_SECONDS,
            verify=verify_ssl,
        )
        response.raise_for_status()

        payload = response.json()
        sites = payload.get("value", {}).get("timeSeries", []) or []

        if not sites:
            return _json_response(
                {
                    "source": "USGS NWIS Instantaneous Values Service",
                    "message": "No recent USGS readings found for the selected state and parameter.",
                    "state_fips": resolved_state_fips,
                    "state_name": state_name,
                    "parameter": parameter_name,
                    "parameter_code": parameter_code,
                    "period_days": days,
                    "records": [],
                    "request_url": response.url,
                }
            )

        records = _extract_latest_records(
            sites=sites,
            max_records=MAX_RECORDS,
        )

        return _json_response(
            {
                "source": "USGS NWIS Instantaneous Values Service",
                "state_fips": resolved_state_fips,
                "state_name": state_name,
                "parameter": parameter_name,
                "parameter_code": parameter_code,
                "period_days": days,
                "record_count": len(records),
                "records": records,
                "request_url": response.url,
                "note": "USGS recent values may be provisional and subject to revision.",
            }
        )

    except requests.Timeout:
        return _json_response(
            {
                "error": "USGS request timed out.",
                "state_fips": resolved_state_fips,
                "parameter": parameter_name,
                "period_days": days,
            }
        )

    except requests.HTTPError as exc:
        return _json_response(
            {
                "error": f"USGS HTTP error: {exc}",
                "status_code": getattr(exc.response, "status_code", None),
                "state_fips": resolved_state_fips,
                "parameter": parameter_name,
                "period_days": days,
            }
        )

    except requests.RequestException as exc:
        return _json_response(
            {
                "error": f"USGS request failed: {exc}",
                "state_fips": resolved_state_fips,
                "parameter": parameter_name,
                "period_days": days,
            }
        )

    except Exception as exc:
        logger.exception("Unexpected USGS tool failure")

        return _json_response(
            {
                "error": f"Unexpected tool failure: {exc}",
                "state_fips": resolved_state_fips,
                "parameter": parameter_name,
                "period_days": days,
            }
        )