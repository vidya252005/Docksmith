#!/usr/bin/env python3
import argparse
import sys
import os

from engine.image import load_image, list_images, delete_image, init_dirs
from engine.builder import build
from engine.runtime import run_container


def cmd_build(args):
    name, tag = args.tag.split(":") if ":" in args.tag else (args.tag, "latest")
    build(
        context_dir=os.path.abspath(args.context),
        name=name,
        tag=tag,
        no_cache=args.no_cache
    )


def cmd_images(args):
    images = list_images()
    if not images:
        print("No images found.")
        return
    print(f"{'NAME':<20} {'TAG':<15} {'ID':<15} {'CREATED'}")
    print("-" * 70)
    for img in images:
        name = img.get("name", "")
        tag = img.get("tag", "")
        digest = img.get("digest", "")
        short_id = digest.replace("sha256:", "")[:12]
        created = img.get("created", "")[:19]
        print(f"{name:<20} {tag:<15} {short_id:<15} {created}")


def cmd_rmi(args):
    name, tag = args.name_tag.split(":") if ":" in args.name_tag else (args.name_tag, "latest")
    try:
        delete_image(name, tag)
        print(f"Deleted {name}:{tag}")
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_run(args):
    name, tag = args.name_tag.split(":") if ":" in args.name_tag else (args.name_tag, "latest")
    try:
        manifest = load_image(name, tag)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse -e overrides
    env_overrides = {}
    if args.env:
        for item in args.env:
            k, _, v = item.partition("=")
            env_overrides[k] = v

    cmd_override = args.cmd if args.cmd else None

    run_container(manifest, cmd_override=cmd_override, env_overrides=env_overrides)


def main():
    init_dirs()
    parser = argparse.ArgumentParser(prog="docksmith")
    subparsers = parser.add_subparsers(dest="command")

    # build
    p_build = subparsers.add_parser("build")
    p_build.add_argument("-t", dest="tag", required=True)
    p_build.add_argument("context")
    p_build.add_argument("--no-cache", action="store_true")
    p_build.set_defaults(func=cmd_build)

    # images
    p_images = subparsers.add_parser("images")
    p_images.set_defaults(func=cmd_images)

    # rmi
    p_rmi = subparsers.add_parser("rmi")
    p_rmi.add_argument("name_tag")
    p_rmi.set_defaults(func=cmd_rmi)

    # run
    p_run = subparsers.add_parser("run")
    p_run.add_argument("name_tag")
    p_run.add_argument("cmd", nargs="*")
    p_run.add_argument("-e", dest="env", action="append")
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
