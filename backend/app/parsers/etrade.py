from datetime import date, datetime

from app.parsers.base import BaseParser, ParseResult


class ETradeParser(BaseParser):
    def can_handle(self, source: str) -> bool:
        return source.lower() in ("etrade", "e-trade", "e_trade")

    def parse(self, raw_data: dict | str) -> ParseResult:
        if isinstance(raw_data, str):
            import json

            try:
                raw_data = json.loads(raw_data)
            except (json.JSONDecodeError, TypeError) as e:
                return ParseResult(errors=[f"Invalid JSON: {e}"])

        records: list[dict] = []
        errors: list[str] = []
        today = date.today()

        grant_count = 0
        vest_event_count = 0
        stock_price_count = 0
        snapshot_count = 0
        holding_count = 0

        # Parse RSU grants
        for grant in raw_data.get("grants", []):
            try:
                grant_id = grant.get("grantId")
                if not grant_id:
                    errors.append("Grant missing grantId, skipped")
                    continue

                records.append(
                    {
                        "table": "rsu_grants",
                        "data": {
                            "id": grant_id,
                            "company": grant.get("company", "Unknown"),
                            "grant_date": grant.get("grantDate"),
                            "total_shares": grant.get("totalShares"),
                            "vested_shares": grant.get("vestedShares"),
                            "unvested_shares": grant.get("unvestedShares"),
                            "sellable_shares": grant.get("sellableShares"),
                            "share_price": grant.get("sharePrice"),
                        },
                    }
                )
                grant_count += 1

                # Parse vest events within this grant
                for event in grant.get("vestEvents", []):
                    try:
                        vest_date = event.get("vestDate")
                        shares = event.get("shares")
                        if not vest_date or shares is None:
                            errors.append(
                                f"Vest event in grant {grant_id} missing date or shares, skipped"
                            )
                            continue

                        records.append(
                            {
                                "table": "vest_events",
                                "data": {
                                    "grant_id": grant_id,
                                    "vest_date": vest_date,
                                    "shares": shares,
                                    "vest_price": event.get("vestPrice"),
                                    "is_actual": event.get("isActual", False),
                                },
                            }
                        )
                        vest_event_count += 1

                    except Exception as e:
                        errors.append(f"Error parsing vest event in grant {grant_id}: {e}")

            except Exception as e:
                errors.append(f"Error parsing grant {grant.get('grantId', '?')}: {e}")

        # Parse holdings / portfolio data
        total_portfolio_value = 0.0
        for holding in raw_data.get("holdings", []):
            try:
                symbol = holding.get("symbol")
                if not symbol:
                    errors.append("Holding missing symbol, skipped")
                    continue

                last_price = holding.get("lastPrice")
                market_value = holding.get("marketValue")

                # Record stock price from lastPrice
                if last_price is not None:
                    records.append(
                        {
                            "table": "stock_prices",
                            "data": {
                                "symbol": symbol,
                                "price_date": today.isoformat(),
                                "close_price": float(last_price),
                                "source": "etrade",
                            },
                        }
                    )
                    stock_price_count += 1

                if market_value is not None:
                    total_portfolio_value += float(market_value)

                holding_count += 1

            except Exception as e:
                errors.append(f"Error parsing holding {holding.get('symbol', '?')}: {e}")

        # Create a balance snapshot for the total portfolio value
        if total_portfolio_value > 0:
            # Use a synthetic account_id for the E-Trade brokerage account
            records.append(
                {
                    "table": "balance_snapshots",
                    "data": {
                        "account_id": "etrade-brokerage",
                        "snapshot_date": today.isoformat(),
                        "balance": total_portfolio_value,
                        "source": "etrade",
                    },
                }
            )
            snapshot_count += 1

        summary = {
            "rsu_grants": grant_count,
            "vest_events": vest_event_count,
            "stock_prices": stock_price_count,
            "holdings": holding_count,
            "balance_snapshots": snapshot_count,
            "total_portfolio_value": total_portfolio_value if total_portfolio_value > 0 else None,
        }

        return ParseResult(records=records, summary=summary, errors=errors)
