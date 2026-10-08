#!/usr/bin/env python3
# Spool picker for Mainsail (added 2026-10-08).
# Called by _SPOOL_PROMPT (Spoolman.cfg) after a filament load. Detaches right
# away so Klipper isn't held up, then reads the spool list from Spoolman and
# sends a Mainsail "action:prompt" dialog with one button per spool through
# Moonraker. Each button runs _SPOOL_PICK ID=<n>, which sets the active spool.
import json
import os
import sys
import urllib.request

SPOOLMAN = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.86.11:7912"
MOONRAKER = "http://127.0.0.1:7125"
MAX_BUTTONS = 12


def get(url):
    with urllib.request.urlopen(url, timeout=8) as r:
        return json.load(r)


def clean(s):
    # RESPOND MSG="..." can't hold quotes; "|" separates prompt fields; ";" starts a gcode comment
    return " ".join(str(s).replace('"', "'").replace("|", "/").replace(";", ",").split())


def respond(lines):
    script = "\n".join('RESPOND TYPE=command MSG="action:%s"' % l for l in lines)
    req = urllib.request.Request(
        MOONRAKER + "/printer/gcode/script",
        data=json.dumps({"script": script}).encode(),
        headers={"Content-Type": "application/json"},
    )
    urllib.request.urlopen(req, timeout=120).read()


def label(sp):
    f = sp.get("filament") or {}
    vendor = (f.get("vendor") or {}).get("name", "")
    parts = [vendor, f.get("name", ""), f.get("material", "")]
    text = " ".join(p for p in parts if p) or "Spool"
    rem = sp.get("remaining_weight")
    if rem is not None:
        text += " - %d g left" % round(rem)
    return clean("%s (spool %d)" % (text, sp["id"]))


def main():
    try:
        spools = get(SPOOLMAN + "/api/v1/spool?allow_archived=false")
    except Exception as e:
        respond(["prompt_begin Spoolman",
                 "prompt_text Couldn't reach Spoolman (%s), so no spool was set." % clean(e),
                 "prompt_footer_button OK|_SPOOL_SKIP|primary",
                 "prompt_show"])
        return
    try:
        active = get(MOONRAKER + "/server/spoolman/spool_id")["result"]["spool_id"]
    except Exception:
        active = None
    spools.sort(key=lambda s: (s.get("last_used") or "", s.get("registered") or ""), reverse=True)
    lines = ["prompt_begin Which spool did you load?"]
    if not spools:
        lines.append("prompt_text There are no spools in Spoolman yet. Add them in the Spoolman page in Home Assistant.")
    else:
        lines.append("prompt_text Tap the spool now in the printer so Spoolman can track how much is left.")
        for sp in spools[:MAX_BUTTONS]:
            color = "primary" if sp["id"] == active else "secondary"
            lines.append("prompt_button %s|_SPOOL_PICK ID=%d|%s" % (label(sp), sp["id"], color))
    lines += ["prompt_footer_button Skip|_SPOOL_SKIP|warning", "prompt_show"]
    respond(lines)


if __name__ == "__main__":
    # Detach so RUN_SHELL_COMMAND returns at once; the dialog is sent after the
    # calling macro finishes (Moonraker queues the RESPONDs behind it).
    if os.fork() > 0:
        sys.exit(0)
    os.setsid()
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(devnull, fd)
    try:
        main()
    except Exception:
        pass
