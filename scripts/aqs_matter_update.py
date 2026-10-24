"""Check for and install firmware updates on the sensors over Matter OTA.

The Matter server acts as the OTA provider. It offers the images described by
the manifests in its --ota-provider-dir, matched to a sensor by vendor and
product ID, so each variant only ever sees its own images. The image travels
over Thread, which for a full image takes several minutes.

The server reports an update as finished whenever the sensor goes back to idle,
which it also does after an abandoned transfer, and an image that never gets
back online is rolled back by the sensor itself. So an update only counts once
the sensor reports the new version, and this waits for that.
"""

import argparse
import asyncio
import json
import os
import sys
import time

import aiohttp

MATTER_SERVER_URL = os.getenv("MATTER_SERVER_URL", "ws://localhost:5580/ws")

# Basic Information cluster (0x0028) attributes of the running firmware
SOFTWARE_VERSION_PATH = "0/40/9"
SOFTWARE_VERSION_STRING_PATH = "0/40/10"

POLL_INTERVAL_S = 15


def parse_args():
    """Parse the subcommand and its arguments from the command line."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default=MATTER_SERVER_URL, help="Matter server WebSocket URL")

    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("check", help="Show the update offered to a node, if any")
    check.add_argument("node_id", type=int, help="Node id to check")
    check.set_defaults(version=None)

    update = commands.add_parser("update", help="Install an update on a node and confirm it took")
    update.add_argument("node_id", type=int, help="Node id to update")
    update.add_argument("version", nargs="?", help="Software version to install, the offered one if omitted")
    update.add_argument(
        "--wait-available",
        type=int,
        default=300,
        metavar="S",
        help="How long to wait for the node to be reachable before starting (default 300)",
    )
    update.add_argument(
        "--verify-timeout",
        type=int,
        default=900,
        metavar="S",
        help="How long to wait for the node to report the new version afterwards; "
        "covers the reboot and the 10 minute rollback window (default 900)",
    )

    return parser.parse_args()


async def request(ws, command, args=None):
    """Send one command and return its result, raising on a server error."""
    await ws.send_json({"message_id": command, "command": command, "args": args or {}})
    while True:
        message = await ws.receive_json()
        if message.get("message_id") != command:
            continue
        if "error_code" in message:
            raise RuntimeError(f"{command} failed: {json.dumps(message)}")
        return message.get("result")


def running_version(node):
    """Return the (number, string) software version a node reports."""
    attributes = node.get("attributes", {})
    return attributes.get(SOFTWARE_VERSION_PATH), attributes.get(SOFTWARE_VERSION_STRING_PATH)


def is_target(node, target):
    """Whether a node runs the target version, given as a number or a version string."""
    number, string = running_version(node)
    return number == target if isinstance(target, int) else string == target


async def wait_available(ws, node_id, timeout_s):
    """Wait until the server can reach the node, returning its latest state.

    After a server restart the node needs a moment to be set up again, and an
    update cannot be announced to a node the server cannot reach.
    """
    deadline = time.monotonic() + timeout_s
    while True:
        node = await request(ws, "get_node", {"node_id": node_id})
        if node.get("available"):
            return node
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Node {node_id} not reachable after {timeout_s} s.")
        print(f"Node {node_id} not reachable yet, waiting...")
        await asyncio.sleep(POLL_INTERVAL_S)


async def wait_for_version(ws, node_id, target, timeout_s):
    """Wait until the node reports the target version, returning whether it did."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        node = await request(ws, "get_node", {"node_id": node_id})
        if node.get("available") and is_target(node, target):
            return True
        await asyncio.sleep(POLL_INTERVAL_S)
    return False


async def run(args):
    """Connect to the Matter server and carry out the requested subcommand.

    Returns the process exit code: 0 when up to date or updated, 1 otherwise.
    """
    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(args.url, heartbeat=30) as ws:
            await ws.receive_json()

            if args.command == "update":
                node = await wait_available(ws, args.node_id, args.wait_available)
            else:
                node = await request(ws, "get_node", {"node_id": args.node_id})
            current, current_string = running_version(node)
            print(f"Node {args.node_id}: running version {current_string} ({current}).")

            if args.version is None:
                # The server offers the highest local image without comparing it to
                # the running version, so the comparison is made here.
                offered = await request(ws, "check_node_update", {"node_id": args.node_id})
                if offered is None or (current is not None and offered["software_version"] <= current):
                    print("Up to date.")
                    return 0
                print(
                    f"Version {offered['software_version_string']} ({offered['software_version']}) "
                    f"available from {offered['update_source']}."
                )
                if args.command == "check":
                    return 0
                target = offered["software_version"]
            else:
                # An explicit version the server does not hold for this node's
                # vendor and product ID fails in update_node, which is wanted: it
                # catches an image published for a different variant.
                target = int(args.version) if args.version.isdigit() else args.version
                if is_target(node, target):
                    print("Already running that version.")
                    return 0

            print("Installing, this takes several minutes over Thread...")
            await request(ws, "update_node", {"node_id": args.node_id, "software_version": target})

            print("Transfer finished, waiting for the node to report the new version...")
            if await wait_for_version(ws, args.node_id, target, args.verify_timeout):
                print(f"Node {args.node_id} updated to {target}.")
                return 0

            node = await request(ws, "get_node", {"node_id": args.node_id})
            number, string = running_version(node)
            print(
                f"Node {args.node_id} still reports {string} ({number}) after {args.verify_timeout} s: "
                "the transfer was abandoned or the new image rolled back.",
                file=sys.stderr,
            )
            return 1


def main():
    """Run the requested subcommand, reporting any server error."""
    args = parse_args()
    try:
        return asyncio.run(run(args))
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
