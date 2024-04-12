from typing import Literal

# TOKENS
token_a = "0xBc7d0108905a22068541A70719Ca9aD5744327eF"
token_b = "0xEDadeB304ebc9e87655F607DE495D024BCD4C310"
weETH = "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee"
wstETH = "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0"

# ------------------------- USERS -------------------------

# Taker API Users
taker_api_users = {
    "protocol": {
        "ion-protocol": {
            "name": "Ion Protocol",
            "permissions": {
                "canExecuteOrders": True,
                "useCases": ["ION_DELEVERAGE"],
            },
            "protocolUser": {
                "source": "ION_PROTOCOL",
                "secret": "e6aae2ac3824ac2f5bd4f251ccc39defd131869824e39dd26a4ae3a6c23b5900",
            },
        },
        "hourglass-protocol": {
            "name": "Hourglass Protocol",
            "permissions": {
                "canExecuteOrders": True,
                "useCases": ["DEFAULT", "HOURGLASS_POINT_LEVERAGE"],
            },
            "protocolUser": {
                "source": "HOURGLASS_PROTOCOL",
                "secret": "e6aae2ac3824ac2f5bd4f251ccc39defd131869824e39dd26a4ae3a6c23b5891",
            },
        },
    },
    "wallet": [
        {
            "name": "user-1",
            "permissions": {"canExecuteOrders": True, "useCases": ["DEFAULT"]},
            "walletUser": {
                "clientId": "user-1-client-id",
                "clientSecret": "user-1-client-secret",
                "wallets": ["*"],
            },
        }
    ],
}


def get_taker_api_protocol_user(
    protocol: Literal["ion-protocol", "hourglass-protocol"]
):
    return taker_api_users["protocol"][protocol]["protocolUser"]


def get_taker_api_wallet_user(name: str):
    for user in taker_api_users["wallet"]:
        if user["name"] == name:
            return user["walletUser"]
    raise Exception(f"User {name} not found in taker_api_users")


# Maker API Users
maker_api_users = [
    {
        "name": "Wintermute",
        "clientId": "wintermute-clown-car",
        "clientSecret": "17-cm",
        "wallets": ["*"],
    },
    {
        "name": "Alameda",
        "clientId": "alameda-clown-car",
        "clientSecret": "18-cm",
        "wallets": ["*"],
    },
]


def get_maker_api_user(name: str):
    for user in maker_api_users:
        if user["name"] == name:
            return user
    raise Exception(f"User {name} not found in maker_api_users")
