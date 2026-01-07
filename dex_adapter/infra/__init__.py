"""
Infrastructure layer for DEX Adapter

Provides:
- RpcClient: HTTP RPC wrapper with retry logic
- Signer: Transaction signing abstraction (local keypair)
- TxBuilder: Transaction assembly and sending
- EVMSigner: EVM transaction signing using web3.py
"""

from .rpc import RpcClient, RpcClientConfig
from .solana_signer import (
    Signer,
    LocalSigner,
    create_signer,
)
from .tx_builder import TxBuilder, TxBuilderConfig

# EVM infrastructure
from .evm_signer import (
    EVMSigner,
    create_web3,
    create_evm_signer,
    get_balance as get_evm_balance,
    get_token_info as get_evm_token_info,
)

__all__ = [
    # Solana infrastructure
    "RpcClient",
    "RpcClientConfig",
    "Signer",
    "LocalSigner",
    "create_signer",
    "TxBuilder",
    "TxBuilderConfig",
    # EVM infrastructure
    "EVMSigner",
    "create_web3",
    "create_evm_signer",
    "get_evm_balance",
    "get_evm_token_info",
]
