import socketio
from typing import Literal, Optional
from src_shared import emit_message
from src_taker import OrderComponents


async def create_rfq(
    ns: socketio.AsyncClientNamespace,
    sio: socketio.AsyncClient,
    *,
    base_asset_address: str,
    quote_asset_address: str,
    base_amount: str = None,
    quote_amount: str = None,
    chain_id: int,
    executor: Literal["MAKER", "TAKER"],
    quote_asset_receiver_address: Optional[str] = None,
    use_case: Literal["DEFAULT", "ION_DELEVERAGE"],
    use_case_metadata: Optional[dict] = None,
):
    if base_amount is None and quote_amount is None:
        raise ValueError("Either base_amount or quote_amount must be provided")
    if base_amount is not None and quote_amount is not None:
        raise ValueError("Only one of base_amount or quote_amount must be provided")

    method = "hg_requestQuote"
    params = {
        "baseAssetAddress": base_asset_address,
        "quoteAssetAddress": quote_asset_address,
        "baseAssetChainId": chain_id,
        "quoteAssetChainId": chain_id,
        "useCase": use_case,
        "executor": executor,
    }
    if use_case:
        params["useCase"] = use_case
    if use_case_metadata:
        params["useCaseMetadata"] = use_case_metadata
    if quote_asset_receiver_address:
        params["quoteAssetReceiverAddress"] = quote_asset_receiver_address
    if base_amount is not None:
        params["baseAmount"] = base_amount
    if quote_amount is not None:
        params["quoteAmount"] = quote_amount

    print(f"Attempting to create RFQ")
    await emit_message(ns, sio, method, params)


async def accept_quote(
    ns: socketio.AsyncClientNamespace,
    sio: socketio.AsyncClient,
    *,
    quote_id: int,
    components: Optional[OrderComponents] = None,
    signature: Optional[str] = None,
):
    method = "hg_acceptQuote"
    if components is None and signature is not None:
        raise ValueError("If signature is provided, components must also be provided")
    if components is not None and signature is None:
        raise ValueError("If components are provided, signature must also be provided")
    params = {
        "quoteId": quote_id,
        "components": components,
        "signature": signature,
    }
    print(f"Attempted to accept quote {quote_id}")
    res = await emit_message(ns, sio, method, params)
    print(res)
