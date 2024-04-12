import socketio
import json
import web3
from uuid_extensions import uuid7str
from typing import Dict, Any, Tuple
from src_taker import (
    SEAPORT_ABI,
    Order,
    OrderComponents,
    OrderParameters,
    dict_int_to_str,
    EIP_712_ORDER_TYPE,
)
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.datastructures import (
    SignedMessage,
)


# https://eips.ethereum.org/EIPS/eip-2098
# Assume yParity is 0 or 1, normalized from the canonical 27 or 28
def to_compact(r, s, yParity):
    return {"r": r, "yParityAndS": (yParity << 255) | s}


def to_canonical(r, yParityAndS):
    return {
        "r": r,
        "s": yParityAndS & ((1 << 255) - 1),
        "yParity": (yParityAndS >> 255),
    }


def etherToGwei(ether: int) -> str:
    return format(ether * 1e18, "f").split(".")[0]


async def emit_message(
    ns: socketio.AsyncClientNamespace,
    sio: socketio.AsyncClient,
    method: str,
    params: Dict[str, Any],
):
    msg_id = uuid7str()
    msg = {"jsonrpc": "2.0", "method": method, "params": params, "id": msg_id}
    print(f"Sending message: {json.dumps(msg, indent=4)}")
    if not hasattr(ns, "sent_messages"):
        raise ValueError("Namespace must have a sent_messages attribute that is a dict")
    ns.sent_messages[msg_id] = msg
    res = await sio.emit("message", msg, namespace=ns.namespace)
    return res


def construct_order_tuple(order: Order):
    return (
        (
            order.parameters.offerer,
            order.parameters.zone,
            [
                (
                    item.itemType.value,
                    item.token,
                    int(item.identifierOrCriteria),
                    int(item.startAmount),
                    int(item.endAmount),
                )
                for item in order.parameters.offer
            ],
            [
                (
                    item.itemType.value,
                    item.token,
                    int(item.identifierOrCriteria),
                    int(item.startAmount),
                    int(item.endAmount),
                    item.recipient,
                )
                for item in order.parameters.consideration
            ],
            order.parameters.orderType.value,
            order.parameters.startTime,
            order.parameters.endTime,
            order.parameters.zoneHash,
            int(order.parameters.salt),
            order.parameters.conduitKey,
            order.parameters.totalOriginalConsiderationItems,
        ),
        order.signature,
    )


def execute_order(w3: web3.Web3, order: Order, pkey: str):
    account = Account.from_key(pkey)
    conduit_key = "0xa8c94ae38b04140794a9394b76ac6d0a83ac0b02000000000000000000000000"
    seaport_contract = w3.eth.contract(
        address="0x00000000000000ADc04C56Bf30aC9d3c0aAF14dC",
        abi=SEAPORT_ABI,
    )

    # Convert order parameters to tuple.
    order_tuple = construct_order_tuple(order)
    fullfillOrder = seaport_contract.functions.fulfillOrder(order_tuple, conduit_key)

    # Execute transaction
    print(f"Address {account.address} is executing order")
    tx = fullfillOrder.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gasPrice": w3.to_wei("100", "gwei"),
            "gas": 1000000,
        }
    )
    signed_txn = w3.eth.account.sign_transaction(tx, pkey)
    txn_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
    print(f"tx hash: {txn_hash.hex()}")

    tx_receipt = w3.eth.wait_for_transaction_receipt(txn_hash)
    if tx_receipt["status"] == 0:
        print("Transaction reverted")
    elif tx_receipt["status"] == 1:
        print("Transaction success!")
    else:
        print(f"Unknown tx status: {tx_receipt['status']}")


def get_message_to_sign(
    order_parameters: OrderParameters,
    counter: int,
) -> str:
    domain_data = {
        "name": "Seaport",
        "version": "1.5",
        "chainId": 1,
        "verifyingContract": "0x00000000000000ADc04C56Bf30aC9d3c0aAF14dC",
    }

    # We need to convert ints to str when signing due to limitations of certain RPC providers
    order_components = {
        **dict_int_to_str(order_parameters.dict()),
        "counter": counter,
        "offer": list(map(lambda x: dict_int_to_str(x.dict()), order_parameters.offer)),
        "consideration": list(
            map(lambda x: dict_int_to_str(x.dict()), order_parameters.consideration)
        ),
    }

    payload = {
        "domain": domain_data,
        "message": order_components,
        "types": EIP_712_ORDER_TYPE,
        "primaryType": "OrderComponents",
    }
    print(json.dumps(payload, indent=4))

    return payload


def int_to_padded_hex(w3: web3.Web3, number: int, nbytes: int):
    # Convert the number to a 32-byte hex string
    # Arguments for to_bytes: length in bytes, byteorder, and signed flag
    byte_representation = number.to_bytes(nbytes, byteorder="big", signed=False)
    hex_string = w3.to_hex(byte_representation)
    return hex_string


def sign_order(*, w3: web3.Web3, pkey, components_raw) -> Tuple[str, str]:
    totalOriginalConsiderationItems = len(components_raw["consideration"])
    parameters = OrderParameters(
        **components_raw,
        totalOriginalConsiderationItems=totalOriginalConsiderationItems,
    )
    components = OrderComponents(
        **components_raw,
        totalOriginalConsiderationItems=totalOriginalConsiderationItems,
    )
    # TODO: get counter from seaport
    full_message = get_message_to_sign(parameters, 0)
    signed_msg: SignedMessage = w3.eth.account.sign_typed_data(
        pkey, full_message=full_message
    )
    compact_sig_dict = to_compact(signed_msg.r, signed_msg.s, signed_msg.v - 27)

    r = int_to_padded_hex(w3, compact_sig_dict["r"], 32)
    yParityAndS = int_to_padded_hex(w3, compact_sig_dict["yParityAndS"], 32)
    compact_signature = "0x" + r[2:] + yParityAndS[2:]
    return {"signature": compact_signature, "components": components.dict()}
