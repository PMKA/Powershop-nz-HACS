"""Powershop API client using Firebase auth and GraphQL."""
import asyncio
import uuid
import logging
import re
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp

from .const import (
    BRAND,
    BRAND_GQL,
    EMAIL_CONNECTOR_URL,
    FIREBASE_API_KEY,
    FIREBASE_REFRESH_URL,
    FIREBASE_SIGN_IN_URL,
    GRAPHQL_URL,
    OTP_VALIDATOR_URL,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GraphQL queries
# ---------------------------------------------------------------------------

_ACCOUNT_VIEWER_QUERY = """
query accountViewer($allowedBrandCodes: [BrandChoices]) {
  viewer {
    givenName
    familyName
    email
    accounts(allowedBrandCodes: $allowedBrandCodes) {
      number
      status
      ... on AccountType {
        id
        number
        properties {
          id
          address
        }
      }
    }
  }
}
"""

_ACCOUNT_QUERY = """
fragment AccountBalanceFragment on AccountType {
  balance(includeAllLedgers: true)
}

query Account($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    id
    ...AccountBalanceFragment
    overdueBalance
    billingOptions {
      nextBillingDate
      currentBillingPeriodStartDate
      currentBillingPeriodEndDate
    }
  }
}
"""

_MEASUREMENTS_QUERY = """
query measurements(
  $accountNumber: String!
  $propertyId: ID!
  $last: Int
  $endOn: Date
  $readingFrequencyType: ReadingFrequencyType!
) {
  account(accountNumber: $accountNumber) {
    id
    property(id: $propertyId) {
      id
      measurements(
        last: $last
        endOn: $endOn
        timezone: "Pacific/Auckland"
        utilityFilters: [{
          electricityFilters: {
            readingDirection: CONSUMPTION
            readingQuality: COMBINED
            readingFrequencyType: $readingFrequencyType
          }
        }]
      ) {
        ... on MeasurementConnection {
          edges {
            node {
              value
              readAt
              ... on IntervalMeasurementType {
                startAt
                endAt
              }
              metaData {
                statistics {
                  type
                  value
                  costInclTax {
                    estimatedAmount
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

_VOUCHERS_QUERY = """
query vouchersForAccount(
  $accountNumber: String!
  $availableBeforeDate: Date
  $availableFromDate: Date
) {
  vouchersForAccount(
    accountNumber: $accountNumber
    redeemableOnly: true
    first: 100
    availableBeforeDate: $availableBeforeDate
    availableFromDate: $availableFromDate
  ) {
    edges {
      node {
        id
        displayName
        availableFrom
        purchasedAt
        voucherValue
        balance
        redemptions {
          claimedAt
          credit {
            grossAmount
          }
        }
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

_MEASUREMENTS_DAILY_RANGE_QUERY = """
query measurementsPeriod(
  $accountNumber: String!
  $propertyId: ID!
  $startOn: Date!
  $endOn: Date!
) {
  account(accountNumber: $accountNumber) {
    id
    property(id: $propertyId) {
      id
      measurements(
        first: 62
        startOn: $startOn
        endOn: $endOn
        timezone: "Pacific/Auckland"
        utilityFilters: [{
          electricityFilters: {
            readingDirection: CONSUMPTION
            readingQuality: COMBINED
            readingFrequencyType: DAY_INTERVAL
          }
        }]
      ) {
        ... on MeasurementConnection {
          edges {
            node {
              value
              readAt
              ... on IntervalMeasurementType {
                startAt
                endAt
              }
              metaData {
                utilityFilters {
                  ... on ElectricityFiltersOutput {
                    readingQuality
                  }
                }
                statistics {
                  type
                  costInclTax {
                    estimatedAmount
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

_AGREEMENTS_QUERY = """
fragment AgreementFields on Agreement {
  displayName
  description
  validFrom
  validTo
  rates {
    label
    displayLabel
    hasDiscount
    formattedRateExcludingTax
    formattedRateIncludingTax
  }
}

query Agreements($accountNumber: String!, $propertyId: ID!) {
  account(accountNumber: $accountNumber) {
    id
    property(id: $propertyId) {
      id
      address
      meterPoints {
        id
        marketIdentifier
        activeAgreement {
          ...AgreementFields
        }
      }
    }
  }
}
"""


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class AuthError(Exception):
    """Raised when authentication fails (email not found, token expired, etc.)."""


class OTPError(Exception):
    """Raised when OTP verification fails."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_rate(formatted: str) -> Optional[float]:
    """Parse a numeric rate value from a formatted string like '23.45 c/kWh'."""
    if not formatted:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)", formatted)
    return float(match.group(1)) if match else None


def _next_billing_periods(
    period_start: str, period_end: str, count: int = 5
) -> List[Dict[str, str]]:
    """Return *count* future billing period date ranges as ``{start, end}`` dicts.

    Periods are assumed to be monthly with the same start/end day each month.
    """
    def _add_months(d: date, n: int) -> date:
        month = d.month - 1 + n
        year = d.year + month // 12
        month = month % 12 + 1
        day = min(d.day, monthrange(year, month)[1])
        return date(year, month, day)

    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    return [
        {
            "start": _add_months(start, i).isoformat(),
            "end": _add_months(end, i).isoformat(),
        }
        for i in range(1, count + 1)
    ]


# ---------------------------------------------------------------------------
# API client
# ---------------------------------------------------------------------------

class PowershopAPIClient:
    """Client for Powershop using Firebase email-OTP auth and GraphQL."""

    def __init__(self, refresh_token: Optional[str] = None) -> None:
        self.refresh_token = refresh_token
        self._id_token: Optional[str] = None
        self._id_token_expires_at: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=30)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    # ------------------------------------------------------------------
    # OTP authentication (step 1 + step 2)
    # ------------------------------------------------------------------

    async def send_otp(self, email: str) -> str:
        """Send a sign-in OTP to *email*. Returns the journeyId."""
        journey_id = str(uuid.uuid4())
        session = await self._get_session()
        payload = {
            "email": email,
            "brand": BRAND,
            "redirectUrl": "https://app.powershop.nz",
            "journeyId": journey_id,
            "otpEnabled": True,
        }
        async with session.post(
            EMAIL_CONNECTOR_URL,
            json=payload,
            headers={"content-type": "application/json", "X-Client-Platform": "web"},
        ) as resp:
            if resp.status == 404:
                raise AuthError("Email address not found on any Powershop account")
            if not resp.ok:
                raise AuthError(f"Failed to send OTP: HTTP {resp.status}")
        return journey_id

    async def verify_otp(self, email: str, otp: str, journey_id: str) -> Dict[str, str]:
        """Verify *otp* and return ``{"id_token": ..., "refresh_token": ...}``."""
        session = await self._get_session()
        payload = {
            "email": email,
            "otp": otp,
            "brand": BRAND,
            "journeyId": journey_id,
        }
        async with session.post(
            OTP_VALIDATOR_URL,
            json=payload,
            headers={"content-type": "application/json", "X-Client-Platform": "web"},
        ) as resp:
            data = await resp.json()
            if not resp.ok:
                raise OTPError(data.get("error", "OTP verification failed"))
            custom_token = data.get("customToken")
            if not custom_token:
                raise OTPError("No custom token returned by OTP validator")

        return await self._exchange_custom_token(custom_token)

    # ------------------------------------------------------------------
    # Firebase token management
    # ------------------------------------------------------------------

    async def _exchange_custom_token(self, custom_token: str) -> Dict[str, str]:
        """Exchange a Firebase custom token for an ID token + refresh token."""
        session = await self._get_session()
        async with session.post(
            f"{FIREBASE_SIGN_IN_URL}?key={FIREBASE_API_KEY}",
            json={"token": custom_token, "returnSecureToken": True},
        ) as resp:
            data = await resp.json()
            if not resp.ok:
                raise AuthError(f"Firebase custom-token exchange failed: {data}")
            id_token = data["idToken"]
            refresh_token = data["refreshToken"]
            expires_in = int(data.get("expiresIn", 3600))

        self._id_token = id_token
        self.refresh_token = refresh_token
        self._id_token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        return {"id_token": id_token, "refresh_token": refresh_token}

    async def _refresh_id_token(self) -> None:
        """Use the stored refresh token to obtain a fresh ID token."""
        if not self.refresh_token:
            raise AuthError("No refresh token – re-authentication required")
        session = await self._get_session()
        async with session.post(
            f"{FIREBASE_REFRESH_URL}?key={FIREBASE_API_KEY}",
            data=f"grant_type=refresh_token&refresh_token={self.refresh_token}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        ) as resp:
            data = await resp.json()
            if not resp.ok:
                raise AuthError(f"Token refresh failed: {data}")
            self._id_token = data["id_token"]
            self.refresh_token = data["refresh_token"]
            expires_in = int(data.get("expires_in", 3600))
            self._id_token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)

    async def _ensure_valid_token(self) -> str:
        """Return a valid ID token, refreshing if necessary."""
        if (
            self._id_token is None
            or self._id_token_expires_at is None
            or datetime.now() >= self._id_token_expires_at
        ):
            await self._refresh_id_token()
        return self._id_token

    # ------------------------------------------------------------------
    # GraphQL
    # ------------------------------------------------------------------

    async def _graphql(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a GraphQL query against the Powershop API."""
        id_token = await self._ensure_valid_token()
        session = await self._get_session()
        payload: Dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        async with session.post(
            GRAPHQL_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {id_token}",
                "content-type": "application/json",
            },
        ) as resp:
            body = await resp.text()
            if not resp.ok:
                _LOGGER.error("GraphQL HTTP %s: %s", resp.status, body)
                raise ValueError(f"GraphQL HTTP {resp.status}: {body[:500]}")
            data = await resp.json(content_type=None)
        if "errors" in data:
            _LOGGER.error("GraphQL errors: %s", data["errors"])
            raise ValueError(data["errors"][0].get("message", "GraphQL error"))
        return data.get("data", {})

    # ------------------------------------------------------------------
    # High-level data methods
    # ------------------------------------------------------------------

    async def get_account_info(self) -> Dict[str, Any]:
        """Return viewer + account list (account numbers, property IDs)."""
        return await self._graphql(
            _ACCOUNT_VIEWER_QUERY, {"allowedBrandCodes": [BRAND_GQL]}
        )

    async def get_account_data(self, account_number: str) -> Dict[str, Any]:
        """Return balance and billing info for *account_number*."""
        data = await self._graphql(_ACCOUNT_QUERY, {"accountNumber": account_number})
        return data.get("account", {})

    async def get_measurements(
        self,
        account_number: str,
        property_id: str,
        last: int,
        end_on: str,
        freq: str,
    ) -> List[Dict[str, Any]]:
        """Return measurement nodes for the given interval.

        *freq* is one of ``HOUR_INTERVAL``, ``DAY_INTERVAL``, ``MONTH_INTERVAL``.
        """
        data = await self._graphql(
            _MEASUREMENTS_QUERY,
            {
                "accountNumber": account_number,
                "propertyId": property_id,
                "last": last,
                "endOn": end_on,
                "readingFrequencyType": freq,
            },
        )
        measurements = (
            data.get("account", {})
            .get("property", {})
            .get("measurements", {})
        )
        if isinstance(measurements, dict):
            return [e["node"] for e in measurements.get("edges", []) if e.get("node")]
        return []

    async def get_measurements_date_range(
        self,
        account_number: str,
        property_id: str,
        start_on: str,
        end_on: str,
    ) -> List[Dict[str, Any]]:
        """Return daily measurement nodes for a specific date range.

        Each node includes ``metaData.utilityFilters.readingQuality`` so callers
        can distinguish ``ACTUAL`` (already metered) from ``ESTIMATED`` readings.
        """
        data = await self._graphql(
            _MEASUREMENTS_DAILY_RANGE_QUERY,
            {
                "accountNumber": account_number,
                "propertyId": property_id,
                "startOn": start_on,
                "endOn": end_on,
            },
        )
        measurements = (
            data.get("account", {})
            .get("property", {})
            .get("measurements", {})
        )
        if isinstance(measurements, dict):
            return [e["node"] for e in measurements.get("edges", []) if e.get("node")]
        return []

    async def get_agreements(
        self, account_number: str, property_id: str
    ) -> Dict[str, Any]:
        """Return active rate agreements for a property."""
        data = await self._graphql(
            _AGREEMENTS_QUERY,
            {"accountNumber": account_number, "propertyId": property_id},
        )
        return data.get("account", {})

    async def get_vouchers(
        self,
        account_number: str,
        available_before: Optional[str] = None,
        available_from: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return redeemable vouchers (packs), optionally filtered by availability window.

        *available_before* and *available_from* correspond to the GraphQL
        ``availableBeforeDate`` / ``availableFromDate`` parameters. Omitting
        both returns every currently-redeemable pack.
        """
        variables: Dict[str, Any] = {"accountNumber": account_number}
        if available_before:
            variables["availableBeforeDate"] = available_before
        if available_from:
            variables["availableFromDate"] = available_from
        data = await self._graphql(_VOUCHERS_QUERY, variables)
        edges = data.get("vouchersForAccount", {}).get("edges", [])
        return [e["node"] for e in edges if e.get("node")]

    async def get_rate_data(
        self, account_number: str, property_id: str
    ) -> Dict[str, Any]:
        """Return a combined dict of balance, rates, usage, and billing gauge data."""
        # Fetch account data, agreements and all redeemable vouchers in parallel
        account_data, agreement_data, voucher_nodes = await asyncio.gather(
            self.get_account_data(account_number),
            self.get_agreements(account_number, property_id),
            self.get_vouchers(account_number),
        )

        raw_balance = account_data.get("balance")
        balance = round(raw_balance / 100, 2) if raw_balance is not None else None
        raw_overdue = account_data.get("overdueBalance")
        overdue_balance = round(raw_overdue / 100, 2) if raw_overdue is not None else None
        billing_options = account_data.get("billingOptions") or {}
        next_billing_date = billing_options.get("nextBillingDate")
        period_start = billing_options.get("currentBillingPeriodStartDate")
        period_end = billing_options.get("currentBillingPeriodEndDate")

        # Extract rates from the first meter point's active agreement
        rate_periods: Dict[str, Any] = {}
        property_node = agreement_data.get("property", {})
        for mp in property_node.get("meterPoints", []):
            agreement = mp.get("activeAgreement") or {}
            for rate in agreement.get("rates", []):
                label = rate.get("displayLabel") or rate.get("label") or "Unknown"
                raw_rate = _parse_rate(rate.get("formattedRateIncludingTax"))
                rate_periods[label] = {
                    "rate": round(raw_rate * 100, 4) if raw_rate is not None else None,
                    "rate_formatted": rate.get("formattedRateIncludingTax"),
                    "rate_excl_tax": rate.get("formattedRateExcludingTax"),
                    "has_discount": rate.get("hasDiscount", False),
                }
            break  # Only process first meter point

        # Compute upcoming billing period date ranges (next 5 months)
        future_periods = (
            _next_billing_periods(period_start, period_end, 5)
            if period_start and period_end
            else []
        )

        # Fetch all measurements + future period vouchers concurrently
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        coros = (
            [
                # hourly today (uses last/endOn — existing query, no readingQuality needed)
                self.get_measurements(account_number, property_id, 24, tomorrow, "HOUR_INTERVAL"),
                # current billing period daily (with readingQuality for USED/EST split)
                self.get_measurements_date_range(
                    account_number, property_id,
                    period_start or (date.today() - timedelta(days=30)).isoformat(),
                    period_end or date.today().isoformat(),
                ),
            ]
            + [
                self.get_measurements_date_range(
                    account_number, property_id, fp["start"], fp["end"]
                )
                for fp in future_periods
            ]
            + [
                # Future period packs: only packs whose availableFrom falls in that window
                self.get_vouchers(
                    account_number,
                    available_before=fp["end"],
                    available_from=fp["start"],
                )
                for fp in future_periods
            ]
        )

        results = await asyncio.gather(*coros)
        n_future = len(future_periods)
        hourly_nodes: List[Dict[str, Any]] = results[0]
        daily_nodes: List[Dict[str, Any]] = results[1]
        future_meas: List[List[Dict[str, Any]]] = list(results[2: 2 + n_future])
        future_vouchers: List[List[Dict[str, Any]]] = list(results[2 + n_future:])

        # ── Usage ──────────────────────────────────────────────────────────
        usage_today_kwh = round(
            sum(float(n.get("value") or 0) for n in hourly_nodes), 3
        )
        usage_period_kwh = round(
            sum(float(n.get("value") or 0) for n in daily_nodes), 3
        )

        # ── Cost split: ACTUAL (USED) vs all days including ESTIMATED (EST) ──
        cost_used_cents = 0.0
        cost_estimated_cents = 0.0
        for node in daily_nodes:
            meta = node.get("metaData") or {}
            node_quality = (meta.get("utilityFilters") or {}).get("readingQuality", "")
            node_cost = sum(
                float((stat.get("costInclTax") or {}).get("estimatedAmount") or 0)
                for stat in meta.get("statistics", [])
            )
            cost_estimated_cents += node_cost
            if node_quality == "ACTUAL":
                cost_used_cents += node_cost

        cost_used_nzd = round(cost_used_cents / 100, 2)
        cost_estimated_nzd = round(cost_estimated_cents / 100, 2)

        # ── Voucher totals (all currently redeemable packs) ────────────────
        voucher_balance_nzd = round(
            sum(float(v.get("balance") or 0) for v in voucher_nodes) / 100, 2
        )
        voucher_list = [
            {
                "id": v.get("id"),
                "name": v.get("displayName"),
                "available_from": v.get("availableFrom"),
                "balance_nzd": round(float(v.get("balance") or 0) / 100, 2),
                "original_value_nzd": round(float(v.get("voucherValue") or 0) / 100, 2),
            }
            for v in voucher_nodes
            if float(v.get("balance") or 0) > 0
        ]

        # ── Gauge calculations: current period ─────────────────────────────
        cost_still_to_buy_nzd = round(
            max(0.0, cost_estimated_nzd - voucher_balance_nzd), 2
        )
        period_coverage_pct = round(
            min(100.0, voucher_balance_nzd / cost_estimated_nzd * 100)
            if cost_estimated_nzd > 0
            else 100.0,
            1,
        )

        # ── Upcoming billing periods ───────────────────────────────────────
        upcoming_periods: List[Dict[str, Any]] = []
        for fp, fmeas, fvouch in zip(future_periods, future_meas, future_vouchers):
            fp_est_cents = sum(
                float((stat.get("costInclTax") or {}).get("estimatedAmount") or 0)
                for node in fmeas
                for stat in (node.get("metaData") or {}).get("statistics", [])
            )
            fp_est_nzd = round(fp_est_cents / 100, 2)
            # Use voucherValue (full original amount) for future packs — balance equals
            # voucherValue for packs not yet redeemed against a future period.
            fp_bought_nzd = round(
                sum(float(v.get("voucherValue") or 0) for v in fvouch) / 100, 2
            )
            fp_still_nzd = round(max(0.0, fp_est_nzd - fp_bought_nzd), 2)
            fp_coverage = round(
                min(100.0, fp_bought_nzd / fp_est_nzd * 100)
                if fp_est_nzd > 0
                else 100.0,
                1,
            )
            upcoming_periods.append(
                {
                    "period_start": fp["start"],
                    "period_end": fp["end"],
                    "cost_estimated_nzd": fp_est_nzd,
                    "voucher_bought_nzd": fp_bought_nzd,
                    "cost_still_to_buy_nzd": fp_still_nzd,
                    "coverage_pct": fp_coverage,
                }
            )

        return {
            "balance": balance,
            "overdue_balance": overdue_balance,
            "next_billing_date": next_billing_date,
            "period_start": period_start,
            "period_end": period_end,
            "rate_periods": rate_periods,
            "account_number": account_number,
            "usage_today_kwh": usage_today_kwh,
            "usage_period_kwh": usage_period_kwh,
            # cost_period_nzd kept as alias for backward compatibility (= EST)
            "cost_period_nzd": cost_estimated_nzd,
            "cost_used_nzd": cost_used_nzd,
            "cost_estimated_nzd": cost_estimated_nzd,
            "cost_still_to_buy_nzd": cost_still_to_buy_nzd,
            "period_coverage_pct": period_coverage_pct,
            "voucher_balance_nzd": voucher_balance_nzd,
            "voucher_list": voucher_list,
            "voucher_count": len(voucher_list),
            "upcoming_periods": upcoming_periods,
        }
