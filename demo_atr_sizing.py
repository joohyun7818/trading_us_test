#!/usr/bin/env python3
"""
Demo script to illustrate ATR-based position sizing differences.

This shows how high-volatility stocks get smaller position sizes
than low-volatility stocks to maintain equal risk exposure.
"""
import asyncio
from unittest.mock import AsyncMock, patch


async def demo_position_sizing():
    """Demonstrate position sizing for different volatility stocks."""
    from api.services.position_sizer import calculate_position_size

    print("=" * 70)
    print("ATR-Based Position Sizing Demonstration")
    print("=" * 70)
    print()
    print("Settings:")
    print("  - Account Equity: $100,000")
    print("  - Risk per Trade: 1% ($1,000)")
    print("  - Hard Stop Multiplier: 2.5x ATR")
    print("  - Signal Score: 75 (good signal, 1.0x multiplier)")
    print()

    account_equity = 100000.0
    signal_score = 75.0

    # Mock database calls
    with patch("api.services.position_sizer.fetch_one", new_callable=AsyncMock) as mock_fetch_one:
        print("-" * 70)
        print("Example 1: High Volatility Stock (e.g., COIN, ALB)")
        print("-" * 70)

        # High volatility: ALB with ATR=$8.50
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.10"},  # max_single_order_pct (10% to show real difference)
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 8.50, "latest_price": 170.0, "sector_id": 1},  # stock info
        ]

        result_high_vol = await calculate_position_size(
            symbol="ALB",
            signal_score=signal_score,
            account_equity=account_equity,
            current_positions=[],
            max_positions=20,
        )

        print(f"Symbol: ALB (High Volatility)")
        print(f"  Current Price: $170.00")
        print(f"  ATR (14-day): ${result_high_vol['atr_14']:.2f}")
        print(f"  Dollar Risk per Share: ${result_high_vol['atr_14'] * 2.5:.2f}")
        print(f"  → Order Amount: ${result_high_vol['order_amount']:.2f}")
        print(f"  → Quantity: {result_high_vol['quantity']} shares")
        print(f"  → Risk per Trade: ${result_high_vol['risk_per_trade']:.2f}")
        print(f"  → Sizing Reason: {result_high_vol['sizing_reason']}")
        print()

        print("-" * 70)
        print("Example 2: Low Volatility Stock (e.g., JNJ, PG)")
        print("-" * 70)

        # Low volatility: JNJ with ATR=$1.20
        mock_fetch_one.side_effect = [
            {"value": "0.01"},  # risk_per_trade_pct
            {"value": "2.5"},  # hard_stop_atr_mult
            {"value": "0.10"},  # max_single_order_pct (10% to show real difference)
            {"value": "0.30"},  # sector_cap_pct
            {"value": "200"},  # min_order_amount
            {"atr_14": 1.20, "latest_price": 160.0, "sector_id": 2},  # stock info
        ]

        result_low_vol = await calculate_position_size(
            symbol="JNJ",
            signal_score=signal_score,
            account_equity=account_equity,
            current_positions=[],
            max_positions=20,
        )

        print(f"Symbol: JNJ (Low Volatility)")
        print(f"  Current Price: $160.00")
        print(f"  ATR (14-day): ${result_low_vol['atr_14']:.2f}")
        print(f"  Dollar Risk per Share: ${result_low_vol['atr_14'] * 2.5:.2f}")
        print(f"  → Order Amount: ${result_low_vol['order_amount']:.2f}")
        print(f"  → Quantity: {result_low_vol['quantity']} shares")
        print(f"  → Risk per Trade: ${result_low_vol['risk_per_trade']:.2f}")
        print(f"  → Sizing Reason: {result_low_vol['sizing_reason']}")
        print()

        print("=" * 70)
        print("Analysis:")
        print("=" * 70)
        high_vol_ratio = result_high_vol['order_amount'] / account_equity * 100
        low_vol_ratio = result_low_vol['order_amount'] / account_equity * 100

        print(f"High Volatility (ALB):")
        print(f"  - Order Size: ${result_high_vol['order_amount']:.2f} ({high_vol_ratio:.2f}% of equity)")
        print(f"  - ATR: ${result_high_vol['atr_14']:.2f} (5.0% of price)")
        print()
        print(f"Low Volatility (JNJ):")
        print(f"  - Order Size: ${result_low_vol['order_amount']:.2f} ({low_vol_ratio:.2f}% of equity)")
        print(f"  - ATR: ${result_low_vol['atr_14']:.2f} (0.75% of price)")
        print()

        ratio = result_low_vol['order_amount'] / result_high_vol['order_amount']
        print(f"JNJ position is {ratio:.1f}x larger than ALB position")
        print(f"This maintains equal risk: both risk ~${result_high_vol['risk_per_trade']:.2f} per trade")
        print()

        print("-" * 70)
        print("Example 3: Signal Score Scaling")
        print("-" * 70)

        # Test different signal scores with moderate volatility stock
        test_cases = [
            (60, "moderate"),
            (75, "good"),
            (85, "strong"),
            (95, "exceptional"),
        ]

        print(f"Symbol: AAPL (Moderate Volatility, Price=$180, ATR=$3.50)")
        print()

        for score, label in test_cases:
            mock_fetch_one.side_effect = [
                {"value": "0.01"},  # risk_per_trade_pct
                {"value": "2.5"},  # hard_stop_atr_mult
                {"value": "0.20"},  # max_single_order_pct (20% to show scaling)
                {"value": "0.30"},  # sector_cap_pct
                {"value": "200"},  # min_order_amount
                {"atr_14": 3.50, "latest_price": 180.0, "sector_id": 3},  # stock info
            ]

            result = await calculate_position_size(
                symbol="AAPL",
                signal_score=score,
                account_equity=account_equity,
                current_positions=[],
                max_positions=20,
            )

            print(f"  Signal Score {score:2d} ({label:12s}): "
                  f"${result['order_amount']:6,.0f} ({result['quantity']:3d} shares)")

        print()
        print("Higher signal scores result in larger positions (up to 1.5x)")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(demo_position_sizing())
