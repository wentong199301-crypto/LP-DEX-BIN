"""
PancakeSwap V3 Contract Addresses and Constants

Provides contract addresses and constants for PancakeSwap V3 liquidity operations.
Supports BSC (Chain ID 56) only.
"""

# PancakeSwap V3 NonfungiblePositionManager address
PANCAKESWAP_POSITION_MANAGER_ADDRESSES = {
    56: "0x46A15B0b27311cedF172AB29E4f4766fbE7F4364",  # BSC
}

# PancakeSwap V3 Factory address
PANCAKESWAP_FACTORY_ADDRESSES = {
    56: "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",  # BSC
}

# Supported chain IDs (BSC only)
PANCAKESWAP_SUPPORTED_CHAINS = [56]

# Chain names
CHAIN_NAMES = {
    56: "BSC",
}

# Fee tiers (in hundredths of a bip, i.e., 1e-6)
# 100 = 0.01%, 500 = 0.05%, 2500 = 0.25%, 10000 = 1%
PANCAKESWAP_FEE_TIERS = [100, 500, 2500, 10000]

# Tick spacing for each fee tier
TICK_SPACING_BY_FEE = {
    100: 1,
    500: 10,
    2500: 50,
    10000: 200,
}
