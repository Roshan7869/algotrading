#!/bin/bash
# Environment variable substitution for Freqtrade configs
# This script replaces ${VAR_NAME} placeholders with actual values from .env

set -e

# Load environment variables from .env
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Function to substitute environment variables in a config file
substitute_env_vars() {
    local config_file=$1
    local temp_file="${config_file}.tmp"
    
    # Use envsubst to replace ${VAR_NAME} with actual values
    envsubst < "$config_file" > "$temp_file"
    
    echo "$temp_file"
}

# Main execution
CONFIG_FILE=$1
FREQTRADE_CMD="${@:2}"

if [ -z "$CONFIG_FILE" ]; then
    echo "Usage: $0 <config_file> <freqtrade_command>"
    exit 1
fi

# Create temporary config with substituted values
TEMP_CONFIG=$(substitute_env_vars "$CONFIG_FILE")

# Run freqtrade with the processed config
docker run --rm \
    -v $(pwd)/user_data:/freqtrade/user_data \
    -v $(pwd)/${TEMP_CONFIG}:/freqtrade/config.json \
    freqtradeorg/freqtrade:stable \
    $FREQTRADE_CMD --config /freqtrade/config.json

# Cleanup
rm -f "$TEMP_CONFIG"
