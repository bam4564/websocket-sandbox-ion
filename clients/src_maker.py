import socketio
from src_shared import emit_message
import json
from src_taker import (
    Order,
)

_NAMESPACE = "/maker"


def get_namespace_and_server_url(env: str) -> [str, str]:
    if env == "local":
        return _NAMESPACE, f"ws://localhost:3100{_NAMESPACE}"
    if env == "staging":
        return _NAMESPACE, f"wss://api-origin-staging-v2.hourglass.com{_NAMESPACE}"
    raise ValueError(f"Unknown environment: {env}")


# ------------------------------ BASE NAMESPACE ------------------------------


class MakerNamespaceBase(socketio.AsyncClientNamespace):

    def __init__(self, *args, **kwargs):
        set_access_token = kwargs.get("set_access_token", None)
        if not set_access_token:
            raise ValueError("set_access_token must be provided")
        del kwargs["set_access_token"]

        super().__init__(*args, **kwargs)

        self.sent_messages = {}
        self.accepted_quotes = []
        self.address = None  # must be set
        self.pkey = None  # must be set
        self.set_access_token = set_access_token

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

    def on_RequestForQuoteBroadcast(self, data):
        print(
            f"EVENT [RequestForQuoteBroadcast]: Received RFQ: {json.dumps(data, indent=4)}"
        )
        return "ACK"

    def on_OrderFulfilled(self, data):
        print(
            f"EVENT [OrderFulfilled]: Received fulfilled order: {json.dumps(data, indent=4)}"
        )
        return "ACK"

    # ------------------------------ JSONRPC Method Handlers ------------------------------
    # These can be overwritten in subclasses to handle successful responses idiosyncratically

    def handle_successful_hg_subscribeToMarket(self, result):
        print(f"Successfully subscribed to market {result}")

    def handle_successful_hg_unsubscribeFromMarket(self, result):
        print(f"Successfully unsubscribed from market {result}")

    def handle_successful_hg_submitQuote(self, result):
        print(f"Successfully submitted quote {result}")

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
        if ori_msg["method"] == "hg_subscribeToMarket":
            self.handle_successful_hg_subscribeToMarket(result)
        elif ori_msg["method"] == "hg_unsubscribeFromMarket":
            self.handle_successful_hg_unsubscribeFromMarket(result)
        elif ori_msg["method"] == "hg_submitQuote":
            self.handle_successful_hg_submitQuote(result)
        else:
            raise Exception(
                f"Unknown method {ori_msg['method']} in sent message {msg_id}"
            )


# ------------------------------ ACTION FUNCTIONS ------------------------------


async def join_market(
    ns: socketio.AsyncClientNamespace, sio: socketio.AsyncClient, market_id
):
    method = "hg_subscribeToMarket"
    params = {
        "marketId": market_id,
    }
    res = await emit_message(ns, sio, method, params)
    print(f"Attempted to subscribe to market {market_id}")
    print(res)


async def leave_market(
    ns: socketio.AsyncClientNamespace, sio: socketio.AsyncClient, market_id
):
    method = "hg_unsubscribeFromMarket"
    params = {
        "marketId": market_id,
    }
    res = await emit_message(ns, sio, method, params)
    print(f"Attempted to unsubscribe to market {market_id}")
    print(res)


async def submit_quote(
    ns: socketio.AsyncClientNamespace,
    sio: socketio.AsyncClient,
    *,
    rfq_id,
    base_amount: str = None,
    quote_amount: str = None,
):
    method = "hg_submitQuote"
    params = {
        "rfqId": rfq_id,
    }
    if base_amount is None and quote_amount is not None:
        params["quoteAmount"] = quote_amount
    elif base_amount is not None and quote_amount is None:
        params["baseAmount"] = base_amount
    else:
        raise ValueError("Either base_amount or quote_amount must be specified")
    res = await emit_message(ns, sio, method, params)
    print("Attempted to submit quote.")
    print(res)
