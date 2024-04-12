import socketio
from typing import Optional, Any
from pydantic import BaseModel
from enum import Enum
from typing import List
import json

_NAMESPACE = "/taker"


def get_namespace_and_server_url(env: str) -> [str, str]:
    if env == "local":
        return _NAMESPACE, f"ws://localhost:3100{_NAMESPACE}"
    if env == "staging":
        return _NAMESPACE, f"wss://api-origin-staging-v2.hourglass.com{_NAMESPACE}"
    raise ValueError(f"Unknown environment: {env}")


class TakerNamespaceBase(socketio.AsyncClientNamespace):

    def __init__(self, *args, **kwargs):
        set_access_token = kwargs.get("set_access_token", None)
        if not set_access_token:
            raise ValueError("set_access_token must be provided")
        del kwargs["set_access_token"]

        super().__init__(*args, **kwargs)

        self.sent_messages = {}
        self.rfqs: List[RFQ] = []
        self.set_access_token = set_access_token

    # ------------------------------ Utility ------------------------------

    def find_rfq_or_throw(self, rfq_id: int):
        for rfq in self.rfqs:
            if rfq.rfqId == rfq_id:
                return rfq
        raise Exception(f"No RFQ found with id {rfq_id}")

    # ------------------------------ Event Handlers ------------------------------

    def on_connect(self):
        print(f"EVENT [connect]: Connected to the {self.namespace} namespace.")

    def on_disconnect(self):
        print(f"EVENT [disconnect]: Disconnected from the {self.namespace} namespace.")

    # ------------------------------ Event Handlers ------------------------------

    def on_AccessToken(self, data):
        print(f"EVENT [AccessToken]: Received access token: {data}")
        self.set_access_token(data["accessToken"])
        return "ACK"

    def on_OrderFulfilled(self, data):
        print(
            f"EVENT [OrderFulfilled]: Received fulfilled order: {json.dumps(data, indent=4)}"
        )
        return "ACK"

    # ------------------------------ JSONRPC Method Handlers ------------------------------

    def on_message(self, data):
        print(f"EVENT [message]: Received message: {data}")
        msg_id = data["id"]
        result = data["result"] if "result" in data else None
        error = data["error"] if "error" in data else None
        jsonrpc = data["jsonrpc"]
        if not jsonrpc == "2.0":
            raise Exception("Invalid JSON-RPC version received from server")
        # handle response based on sent messages
        if not msg_id in self.sent_messages:
            raise Exception(f"Received message with id: {msg_id} that was never sent")
        ori_msg = self.sent_messages[msg_id]
        # handle errors
        if error:
            print(f"For request {msg_id} received error: {error}")
            return
        # handle results
        if ori_msg["method"] == "hg_requestQuote":
            print(f"Successfully requested quote {result}")
            self.rfqs.append(RFQ(**result))
        elif ori_msg["method"] == "hg_acceptQuote":
            print(f"Successfully accepted quote {result}")
        else:
            raise Exception(
                f"Unknown method {ori_msg['method']} in sent message {msg_id}"
            )


class TokenType(Enum):
    ERC20 = "ERC20"
    ERC721 = "ERC721"
    ERC1155 = "ERC1155"


class Chain(Enum):
    Ethereum = "Ethereum"


class Erc20(BaseModel):
    chain: Chain
    address: str
    name: str
    symbol: str
    description: Optional[str]
    tokenDecimals: int


class RFQ(BaseModel):
    rfqId: int
    quoteAssetReceiverAddress: Optional[str] = None
    baseAssetChainId: int
    quoteAssetChainId: int
    baseAssetAddress: str
    quoteAssetAddress: str
    baseAmount: Optional[str]
    quoteAmount: Optional[str]
    ttlMsecs: int
    executor: str
    useCase: str


EIP_712_ORDER_TYPE = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
        {"name": "verifyingContract", "type": "address"},
    ],
    "OrderComponents": [
        {"name": "offerer", "type": "address"},
        {"name": "zone", "type": "address"},
        {"name": "offer", "type": "OfferItem[]"},
        {"name": "consideration", "type": "ConsiderationItem[]"},
        {"name": "orderType", "type": "uint8"},
        {"name": "startTime", "type": "uint256"},
        {"name": "endTime", "type": "uint256"},
        {"name": "zoneHash", "type": "bytes32"},
        {"name": "salt", "type": "uint256"},
        {"name": "conduitKey", "type": "bytes32"},
        {"name": "counter", "type": "uint256"},
    ],
    "OfferItem": [
        {"name": "itemType", "type": "uint8"},
        {"name": "token", "type": "address"},
        {"name": "identifierOrCriteria", "type": "uint256"},
        {"name": "startAmount", "type": "uint256"},
        {"name": "endAmount", "type": "uint256"},
    ],
    "ConsiderationItem": [
        {"name": "itemType", "type": "uint8"},
        {"name": "token", "type": "address"},
        {"name": "identifierOrCriteria", "type": "uint256"},
        {"name": "startAmount", "type": "uint256"},
        {"name": "endAmount", "type": "uint256"},
        {"name": "recipient", "type": "address"},
    ],
}


def with_int_to_str(element: Any):
    if isinstance(element, dict):
        return {k: with_int_to_str(v) for k, v in element.items()}
    elif isinstance(element, list):
        return [with_int_to_str(el) for el in element]
    elif isinstance(element, int):
        return str(element)
    return element


def dict_int_to_str(d: dict):
    return {key: str(val) if isinstance(val, int) else val for key, val in d.items()}


class BaseModelWithEnumValues(BaseModel):
    """
    Using this helper model class as the built-in pydantic use_enum_values breaks type guarantees
    when accessing enums on the model directly

    Args:
        BaseModel (_type_): _description_
    """

    def dict(self, *args, **kwargs):
        resolved_dict = super().dict(**kwargs)

        return with_enum_values(resolved_dict)


def with_enum_values(element):
    if isinstance(element, dict):
        return {k: with_enum_values(v) for k, v in element.items()}
    elif isinstance(element, list):
        return [with_enum_values(el) for el in element]
    elif isinstance(element, Enum):
        return element.value
    return element


class OrderType(Enum):
    FULL_OPEN = 0  # No partial fills, anyone can execute
    PARTIAL_OPEN = 1  # Partial fills supported, anyone can execute
    FULL_RESTRICTED = 2  # No partial fills, only offerer or zone can execute
    PARTIAL_RESTRICTED = 3  # Partial fills supported, only offerer or zone can execute


class ItemType(Enum):
    NATIVE = 0
    ERC20 = 1
    ERC721 = 2
    ERC1155 = 3
    ERC721_WITH_CRITERIA = 4
    ERC1155_WITH_CRITERIA = 5


class OfferItem(BaseModelWithEnumValues):
    itemType: ItemType
    token: str
    identifierOrCriteria: str
    startAmount: str
    endAmount: str


class ConsiderationItem(BaseModelWithEnumValues):
    itemType: ItemType
    token: str
    identifierOrCriteria: str
    startAmount: str
    endAmount: str
    recipient: str


class OrderParameters(BaseModelWithEnumValues):
    offerer: str
    zone: str
    orderType: OrderType
    startTime: int
    endTime: int
    salt: str
    offer: list[OfferItem]
    consideration: list[ConsiderationItem]
    zoneHash: str
    totalOriginalConsiderationItems: int
    conduitKey: str


class OrderComponents(OrderParameters):
    counter: str


class Order(BaseModel):
    parameters: OrderParameters
    signature: str


SEAPORT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "conduitController", "type": "address"}
        ],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },
    {"inputs": [], "name": "BadContractSignature", "type": "error"},
    {"inputs": [], "name": "BadFraction", "type": "error"},
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "BadReturnValueFromERC20OnTransfer",
        "type": "error",
    },
    {
        "inputs": [{"internalType": "uint8", "name": "v", "type": "uint8"}],
        "name": "BadSignatureV",
        "type": "error",
    },
    {"inputs": [], "name": "ConsiderationCriteriaResolverOutOfRange", "type": "error"},
    {
        "inputs": [
            {"internalType": "uint256", "name": "orderIndex", "type": "uint256"},
            {
                "internalType": "uint256",
                "name": "considerationIndex",
                "type": "uint256",
            },
            {"internalType": "uint256", "name": "shortfallAmount", "type": "uint256"},
        ],
        "name": "ConsiderationNotMet",
        "type": "error",
    },
    {"inputs": [], "name": "CriteriaNotEnabledForItem", "type": "error"},
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256[]", "name": "identifiers", "type": "uint256[]"},
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"},
        ],
        "name": "ERC1155BatchTransferGenericFailure",
        "type": "error",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "EtherTransferGenericFailure",
        "type": "error",
    },
    {"inputs": [], "name": "InexactFraction", "type": "error"},
    {"inputs": [], "name": "InsufficientEtherSupplied", "type": "error"},
    {"inputs": [], "name": "InvalidBasicOrderParameterEncoding", "type": "error"},
    {
        "inputs": [{"internalType": "address", "name": "conduit", "type": "address"}],
        "name": "InvalidCallToConduit",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidCanceller", "type": "error"},
    {
        "inputs": [
            {"internalType": "bytes32", "name": "conduitKey", "type": "bytes32"},
            {"internalType": "address", "name": "conduit", "type": "address"},
        ],
        "name": "InvalidConduit",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidERC721TransferAmount", "type": "error"},
    {"inputs": [], "name": "InvalidFulfillmentComponentData", "type": "error"},
    {
        "inputs": [{"internalType": "uint256", "name": "value", "type": "uint256"}],
        "name": "InvalidMsgValue",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidProof", "type": "error"},
    {
        "inputs": [{"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}],
        "name": "InvalidRestrictedOrder",
        "type": "error",
    },
    {"inputs": [], "name": "InvalidSignature", "type": "error"},
    {"inputs": [], "name": "InvalidSigner", "type": "error"},
    {"inputs": [], "name": "InvalidTime", "type": "error"},
    {
        "inputs": [],
        "name": "MismatchedFulfillmentOfferAndConsiderationComponents",
        "type": "error",
    },
    {
        "inputs": [{"internalType": "enum Side", "name": "side", "type": "uint8"}],
        "name": "MissingFulfillmentComponentOnAggregation",
        "type": "error",
    },
    {"inputs": [], "name": "MissingItemAmount", "type": "error"},
    {"inputs": [], "name": "MissingOriginalConsiderationItems", "type": "error"},
    {
        "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
        "name": "NoContract",
        "type": "error",
    },
    {"inputs": [], "name": "NoReentrantCalls", "type": "error"},
    {"inputs": [], "name": "NoSpecifiedOrdersAvailable", "type": "error"},
    {
        "inputs": [],
        "name": "OfferAndConsiderationRequiredOnFulfillment",
        "type": "error",
    },
    {"inputs": [], "name": "OfferCriteriaResolverOutOfRange", "type": "error"},
    {
        "inputs": [{"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}],
        "name": "OrderAlreadyFilled",
        "type": "error",
    },
    {"inputs": [], "name": "OrderCriteriaResolverOutOfRange", "type": "error"},
    {
        "inputs": [{"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}],
        "name": "OrderIsCancelled",
        "type": "error",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}],
        "name": "OrderPartiallyFilled",
        "type": "error",
    },
    {"inputs": [], "name": "PartialFillsNotEnabledForOrder", "type": "error"},
    {
        "inputs": [
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "identifier", "type": "uint256"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "TokenTransferGenericFailure",
        "type": "error",
    },
    {"inputs": [], "name": "UnresolvedConsiderationCriteria", "type": "error"},
    {"inputs": [], "name": "UnresolvedOfferCriteria", "type": "error"},
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "newCounter",
                "type": "uint256",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "offerer",
                "type": "address",
            },
        ],
        "name": "CounterIncremented",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "bytes32",
                "name": "orderHash",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "offerer",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "zone",
                "type": "address",
            },
        ],
        "name": "OrderCancelled",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "bytes32",
                "name": "orderHash",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "offerer",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "zone",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "address",
                "name": "recipient",
                "type": "address",
            },
            {
                "components": [
                    {
                        "internalType": "enum ItemType",
                        "name": "itemType",
                        "type": "uint8",
                    },
                    {"internalType": "address", "name": "token", "type": "address"},
                    {
                        "internalType": "uint256",
                        "name": "identifier",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                ],
                "indexed": False,
                "internalType": "struct SpentItem[]",
                "name": "offer",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "internalType": "enum ItemType",
                        "name": "itemType",
                        "type": "uint8",
                    },
                    {"internalType": "address", "name": "token", "type": "address"},
                    {
                        "internalType": "uint256",
                        "name": "identifier",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "amount", "type": "uint256"},
                    {
                        "internalType": "address payable",
                        "name": "recipient",
                        "type": "address",
                    },
                ],
                "indexed": False,
                "internalType": "struct ReceivedItem[]",
                "name": "consideration",
                "type": "tuple[]",
            },
        ],
        "name": "OrderFulfilled",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": False,
                "internalType": "bytes32",
                "name": "orderHash",
                "type": "bytes32",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "offerer",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "zone",
                "type": "address",
            },
        ],
        "name": "OrderValidated",
        "type": "event",
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {"internalType": "address", "name": "zone", "type": "address"},
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifierOrCriteria",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endAmount",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OfferItem[]",
                        "name": "offer",
                        "type": "tuple[]",
                    },
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifierOrCriteria",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ConsiderationItem[]",
                        "name": "consideration",
                        "type": "tuple[]",
                    },
                    {
                        "internalType": "enum OrderType",
                        "name": "orderType",
                        "type": "uint8",
                    },
                    {"internalType": "uint256", "name": "startTime", "type": "uint256"},
                    {"internalType": "uint256", "name": "endTime", "type": "uint256"},
                    {"internalType": "bytes32", "name": "zoneHash", "type": "bytes32"},
                    {"internalType": "uint256", "name": "salt", "type": "uint256"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                    {"internalType": "uint256", "name": "counter", "type": "uint256"},
                ],
                "internalType": "struct OrderComponents[]",
                "name": "orders",
                "type": "tuple[]",
            }
        ],
        "name": "cancel",
        "outputs": [{"internalType": "bool", "name": "cancelled", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "uint120", "name": "numerator", "type": "uint120"},
                    {
                        "internalType": "uint120",
                        "name": "denominator",
                        "type": "uint120",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                    {"internalType": "bytes", "name": "extraData", "type": "bytes"},
                ],
                "internalType": "struct AdvancedOrder",
                "name": "advancedOrder",
                "type": "tuple",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "enum Side", "name": "side", "type": "uint8"},
                    {"internalType": "uint256", "name": "index", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "identifier",
                        "type": "uint256",
                    },
                    {
                        "internalType": "bytes32[]",
                        "name": "criteriaProof",
                        "type": "bytes32[]",
                    },
                ],
                "internalType": "struct CriteriaResolver[]",
                "name": "criteriaResolvers",
                "type": "tuple[]",
            },
            {
                "internalType": "bytes32",
                "name": "fulfillerConduitKey",
                "type": "bytes32",
            },
            {"internalType": "address", "name": "recipient", "type": "address"},
        ],
        "name": "fulfillAdvancedOrder",
        "outputs": [{"internalType": "bool", "name": "fulfilled", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "uint120", "name": "numerator", "type": "uint120"},
                    {
                        "internalType": "uint120",
                        "name": "denominator",
                        "type": "uint120",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                    {"internalType": "bytes", "name": "extraData", "type": "bytes"},
                ],
                "internalType": "struct AdvancedOrder[]",
                "name": "advancedOrders",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "enum Side", "name": "side", "type": "uint8"},
                    {"internalType": "uint256", "name": "index", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "identifier",
                        "type": "uint256",
                    },
                    {
                        "internalType": "bytes32[]",
                        "name": "criteriaProof",
                        "type": "bytes32[]",
                    },
                ],
                "internalType": "struct CriteriaResolver[]",
                "name": "criteriaResolvers",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "itemIndex", "type": "uint256"},
                ],
                "internalType": "struct FulfillmentComponent[][]",
                "name": "offerFulfillments",
                "type": "tuple[][]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "itemIndex", "type": "uint256"},
                ],
                "internalType": "struct FulfillmentComponent[][]",
                "name": "considerationFulfillments",
                "type": "tuple[][]",
            },
            {
                "internalType": "bytes32",
                "name": "fulfillerConduitKey",
                "type": "bytes32",
            },
            {"internalType": "address", "name": "recipient", "type": "address"},
            {"internalType": "uint256", "name": "maximumFulfilled", "type": "uint256"},
        ],
        "name": "fulfillAvailableAdvancedOrders",
        "outputs": [
            {"internalType": "bool[]", "name": "availableOrders", "type": "bool[]"},
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifier",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ReceivedItem",
                        "name": "item",
                        "type": "tuple",
                    },
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                ],
                "internalType": "struct Execution[]",
                "name": "executions",
                "type": "tuple[]",
            },
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                ],
                "internalType": "struct Order[]",
                "name": "orders",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "itemIndex", "type": "uint256"},
                ],
                "internalType": "struct FulfillmentComponent[][]",
                "name": "offerFulfillments",
                "type": "tuple[][]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "uint256", "name": "itemIndex", "type": "uint256"},
                ],
                "internalType": "struct FulfillmentComponent[][]",
                "name": "considerationFulfillments",
                "type": "tuple[][]",
            },
            {
                "internalType": "bytes32",
                "name": "fulfillerConduitKey",
                "type": "bytes32",
            },
            {"internalType": "uint256", "name": "maximumFulfilled", "type": "uint256"},
        ],
        "name": "fulfillAvailableOrders",
        "outputs": [
            {"internalType": "bool[]", "name": "availableOrders", "type": "bool[]"},
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifier",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ReceivedItem",
                        "name": "item",
                        "type": "tuple",
                    },
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                ],
                "internalType": "struct Execution[]",
                "name": "executions",
                "type": "tuple[]",
            },
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "internalType": "address",
                        "name": "considerationToken",
                        "type": "address",
                    },
                    {
                        "internalType": "uint256",
                        "name": "considerationIdentifier",
                        "type": "uint256",
                    },
                    {
                        "internalType": "uint256",
                        "name": "considerationAmount",
                        "type": "uint256",
                    },
                    {
                        "internalType": "address payable",
                        "name": "offerer",
                        "type": "address",
                    },
                    {"internalType": "address", "name": "zone", "type": "address"},
                    {
                        "internalType": "address",
                        "name": "offerToken",
                        "type": "address",
                    },
                    {
                        "internalType": "uint256",
                        "name": "offerIdentifier",
                        "type": "uint256",
                    },
                    {
                        "internalType": "uint256",
                        "name": "offerAmount",
                        "type": "uint256",
                    },
                    {
                        "internalType": "enum BasicOrderType",
                        "name": "basicOrderType",
                        "type": "uint8",
                    },
                    {"internalType": "uint256", "name": "startTime", "type": "uint256"},
                    {"internalType": "uint256", "name": "endTime", "type": "uint256"},
                    {"internalType": "bytes32", "name": "zoneHash", "type": "bytes32"},
                    {"internalType": "uint256", "name": "salt", "type": "uint256"},
                    {
                        "internalType": "bytes32",
                        "name": "offererConduitKey",
                        "type": "bytes32",
                    },
                    {
                        "internalType": "bytes32",
                        "name": "fulfillerConduitKey",
                        "type": "bytes32",
                    },
                    {
                        "internalType": "uint256",
                        "name": "totalOriginalAdditionalRecipients",
                        "type": "uint256",
                    },
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct AdditionalRecipient[]",
                        "name": "additionalRecipients",
                        "type": "tuple[]",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                ],
                "internalType": "struct BasicOrderParameters",
                "name": "parameters",
                "type": "tuple",
            }
        ],
        "name": "fulfillBasicOrder",
        "outputs": [{"internalType": "bool", "name": "fulfilled", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                ],
                "internalType": "struct Order",
                "name": "order",
                "type": "tuple",
            },
            {
                "internalType": "bytes32",
                "name": "fulfillerConduitKey",
                "type": "bytes32",
            },
        ],
        "name": "fulfillOrder",
        "outputs": [{"internalType": "bool", "name": "fulfilled", "type": "bool"}],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "offerer", "type": "address"}],
        "name": "getCounter",
        "outputs": [{"internalType": "uint256", "name": "counter", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {"internalType": "address", "name": "zone", "type": "address"},
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifierOrCriteria",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endAmount",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OfferItem[]",
                        "name": "offer",
                        "type": "tuple[]",
                    },
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifierOrCriteria",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endAmount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ConsiderationItem[]",
                        "name": "consideration",
                        "type": "tuple[]",
                    },
                    {
                        "internalType": "enum OrderType",
                        "name": "orderType",
                        "type": "uint8",
                    },
                    {"internalType": "uint256", "name": "startTime", "type": "uint256"},
                    {"internalType": "uint256", "name": "endTime", "type": "uint256"},
                    {"internalType": "bytes32", "name": "zoneHash", "type": "bytes32"},
                    {"internalType": "uint256", "name": "salt", "type": "uint256"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                    {"internalType": "uint256", "name": "counter", "type": "uint256"},
                ],
                "internalType": "struct OrderComponents",
                "name": "order",
                "type": "tuple",
            }
        ],
        "name": "getOrderHash",
        "outputs": [
            {"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "orderHash", "type": "bytes32"}],
        "name": "getOrderStatus",
        "outputs": [
            {"internalType": "bool", "name": "isValidated", "type": "bool"},
            {"internalType": "bool", "name": "isCancelled", "type": "bool"},
            {"internalType": "uint256", "name": "totalFilled", "type": "uint256"},
            {"internalType": "uint256", "name": "totalSize", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "incrementCounter",
        "outputs": [
            {"internalType": "uint256", "name": "newCounter", "type": "uint256"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "information",
        "outputs": [
            {"internalType": "string", "name": "version", "type": "string"},
            {"internalType": "bytes32", "name": "domainSeparator", "type": "bytes32"},
            {"internalType": "address", "name": "conduitController", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "uint120", "name": "numerator", "type": "uint120"},
                    {
                        "internalType": "uint120",
                        "name": "denominator",
                        "type": "uint120",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                    {"internalType": "bytes", "name": "extraData", "type": "bytes"},
                ],
                "internalType": "struct AdvancedOrder[]",
                "name": "advancedOrders",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "internalType": "uint256",
                        "name": "orderIndex",
                        "type": "uint256",
                    },
                    {"internalType": "enum Side", "name": "side", "type": "uint8"},
                    {"internalType": "uint256", "name": "index", "type": "uint256"},
                    {
                        "internalType": "uint256",
                        "name": "identifier",
                        "type": "uint256",
                    },
                    {
                        "internalType": "bytes32[]",
                        "name": "criteriaProof",
                        "type": "bytes32[]",
                    },
                ],
                "internalType": "struct CriteriaResolver[]",
                "name": "criteriaResolvers",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "orderIndex",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "itemIndex",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct FulfillmentComponent[]",
                        "name": "offerComponents",
                        "type": "tuple[]",
                    },
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "orderIndex",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "itemIndex",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct FulfillmentComponent[]",
                        "name": "considerationComponents",
                        "type": "tuple[]",
                    },
                ],
                "internalType": "struct Fulfillment[]",
                "name": "fulfillments",
                "type": "tuple[]",
            },
        ],
        "name": "matchAdvancedOrders",
        "outputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifier",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ReceivedItem",
                        "name": "item",
                        "type": "tuple",
                    },
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                ],
                "internalType": "struct Execution[]",
                "name": "executions",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                ],
                "internalType": "struct Order[]",
                "name": "orders",
                "type": "tuple[]",
            },
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "orderIndex",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "itemIndex",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct FulfillmentComponent[]",
                        "name": "offerComponents",
                        "type": "tuple[]",
                    },
                    {
                        "components": [
                            {
                                "internalType": "uint256",
                                "name": "orderIndex",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "itemIndex",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct FulfillmentComponent[]",
                        "name": "considerationComponents",
                        "type": "tuple[]",
                    },
                ],
                "internalType": "struct Fulfillment[]",
                "name": "fulfillments",
                "type": "tuple[]",
            },
        ],
        "name": "matchOrders",
        "outputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "enum ItemType",
                                "name": "itemType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint256",
                                "name": "identifier",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256",
                            },
                            {
                                "internalType": "address payable",
                                "name": "recipient",
                                "type": "address",
                            },
                        ],
                        "internalType": "struct ReceivedItem",
                        "name": "item",
                        "type": "tuple",
                    },
                    {"internalType": "address", "name": "offerer", "type": "address"},
                    {
                        "internalType": "bytes32",
                        "name": "conduitKey",
                        "type": "bytes32",
                    },
                ],
                "internalType": "struct Execution[]",
                "name": "executions",
                "type": "tuple[]",
            }
        ],
        "stateMutability": "payable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [
            {"internalType": "string", "name": "contractName", "type": "string"}
        ],
        "stateMutability": "pure",
        "type": "function",
    },
    {
        "inputs": [
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "offerer",
                                "type": "address",
                            },
                            {
                                "internalType": "address",
                                "name": "zone",
                                "type": "address",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                ],
                                "internalType": "struct OfferItem[]",
                                "name": "offer",
                                "type": "tuple[]",
                            },
                            {
                                "components": [
                                    {
                                        "internalType": "enum ItemType",
                                        "name": "itemType",
                                        "type": "uint8",
                                    },
                                    {
                                        "internalType": "address",
                                        "name": "token",
                                        "type": "address",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "identifierOrCriteria",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "startAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "uint256",
                                        "name": "endAmount",
                                        "type": "uint256",
                                    },
                                    {
                                        "internalType": "address payable",
                                        "name": "recipient",
                                        "type": "address",
                                    },
                                ],
                                "internalType": "struct ConsiderationItem[]",
                                "name": "consideration",
                                "type": "tuple[]",
                            },
                            {
                                "internalType": "enum OrderType",
                                "name": "orderType",
                                "type": "uint8",
                            },
                            {
                                "internalType": "uint256",
                                "name": "startTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "uint256",
                                "name": "endTime",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "zoneHash",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "salt",
                                "type": "uint256",
                            },
                            {
                                "internalType": "bytes32",
                                "name": "conduitKey",
                                "type": "bytes32",
                            },
                            {
                                "internalType": "uint256",
                                "name": "totalOriginalConsiderationItems",
                                "type": "uint256",
                            },
                        ],
                        "internalType": "struct OrderParameters",
                        "name": "parameters",
                        "type": "tuple",
                    },
                    {"internalType": "bytes", "name": "signature", "type": "bytes"},
                ],
                "internalType": "struct Order[]",
                "name": "orders",
                "type": "tuple[]",
            }
        ],
        "name": "validate",
        "outputs": [{"internalType": "bool", "name": "validated", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]
