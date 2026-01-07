"""
Uniswap Contract Addresses and Constants

Provides contract addresses and constants for Uniswap V3 and V4 liquidity operations.
Supports Ethereum Mainnet only.
"""

# =========================================================================
# Uniswap V3 Contracts (Ethereum Mainnet)
# =========================================================================

# Uniswap V3 NonfungiblePositionManager address
UNISWAP_V3_POSITION_MANAGER_ADDRESSES = {
    1: "0xC36442b4a4522E871399CD717aBDD847Ab11FE88",   # Ethereum Mainnet
}

# Uniswap V3 Factory address
UNISWAP_V3_FACTORY_ADDRESSES = {
    1: "0x1F98431c8aD98523631AE4a59f267346ea31F984",   # Ethereum Mainnet
}

# =========================================================================
# Uniswap V4 Contracts (Ethereum Mainnet)
# =========================================================================

# Uniswap V4 PoolManager address (singleton, CREATE2 deterministic)
UNISWAP_V4_POOL_MANAGER_ADDRESSES = {
    1: "0x000000000004444c5dc75cB358380D2e3dE08A90",   # Ethereum Mainnet
}

# Uniswap V4 PositionManager address
UNISWAP_V4_POSITION_MANAGER_ADDRESSES = {
    1: "0xbD216513d74C8cf14cf4747E6AaA6420FF64ee9e",   # Ethereum Mainnet
}

# =========================================================================
# Common Constants
# =========================================================================

# Fee tiers (in hundredths of a bip, i.e., 1e-6)
# 100 = 0.01%, 500 = 0.05%, 3000 = 0.30%, 10000 = 1%
UNISWAP_FEE_TIERS = [100, 500, 3000, 10000]

# Tick spacing for each fee tier
TICK_SPACING_BY_FEE = {
    100: 1,
    500: 10,
    3000: 60,
    10000: 200,
}

# Supported chain IDs (Ethereum only)
UNISWAP_SUPPORTED_CHAINS = [1]

# Chain names
CHAIN_NAMES = {
    1: "Ethereum",
}

# Native ETH address for V4 (address(0))
NATIVE_ETH_ADDRESS = "0x0000000000000000000000000000000000000000"

# No hooks address
NO_HOOKS_ADDRESS = "0x0000000000000000000000000000000000000000"
