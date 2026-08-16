"""
Tests for Trade Encoder and Learning Loop
"""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from knowledge.trade_encoder import encode_trade_query, encode_trade_outcome


def test_encode_trade_query_long():
    query = encode_trade_query(pair="BTC/USDT", side="long")
    assert "BTC" in query
    assert "bullish" in query or "long" in query


def test_encode_trade_query_short():
    query = encode_trade_query(pair="ETH/USDT", side="short")
    assert "ETH" in query
    assert "bearish" in query or "short" in query


def test_encode_trade_query_with_market_condition():
    query = encode_trade_query(pair="BTC/USDT", side="long", market_condition="trending")
    assert "trending" in query or "trend" in query


def test_encode_trade_query_with_signal_type():
    query = encode_trade_query(pair="BTC/USDT", side="long", signal_type="breakout")
    assert "breakout" in query


def test_encode_trade_query_with_strategy():
    query = encode_trade_query(pair="BTC/USDT", side="long", strategy="AroonMomentum")
    assert "AroonMomentum" in query


def test_encode_trade_query_with_indicators():
    query = encode_trade_query(pair="BTC/USDT", side="long", indicators={"RSI": 30, "volume": 50000})
    assert "RSI" in query
    assert "30" in query


def test_encode_trade_outcome():
    outcome = encode_trade_outcome("BTC/USDT", "long", 150.0, 2.5, "Test Setup", "trending", "test")
    assert outcome["pair"] == "BTC/USDT"
    assert outcome["pnl"] == 150.0
    assert outcome["r_multiple"] == 2.5
    assert outcome["setup_name"] == "Test Setup"
    assert "timestamp" in outcome


def test_encode_trade_outcome_loss():
    outcome = encode_trade_outcome("ETH/USDT", "short", -50.0, -1.0, "Loss Setup")
    assert outcome["pnl"] == -50.0
    assert outcome["r_multiple"] == -1.0


def test_encode_trade_query_empty_pair():
    query = encode_trade_query(side="long")
    assert "crypto" in query
