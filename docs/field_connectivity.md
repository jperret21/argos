# Field connectivity guide

How to connect the Mac running Argos to the Seestar away from the home
network, and what still works (or not) without internet.

## What actually needs what

| Feature | Needs the Seestar | Needs internet |
|---|---|---|
| Mount / camera / focuser / filter wheel control (Alpaca :32323) | yes | no |
| Manual jog (native JSON-RPC :4700) | yes | no |
| Plate solving (ASTAP, local star database) | no | **no** |
| Stellarium telescope control (local server) | no | no |
| Messier, NGC and IC target names | no — **built in** | no |
| AAVSO VSX/VSP catalogs (photometry overlays) | no | yes — **cached** |

Plate solving is fully offline: ASTAP and its database live on the Mac. Messier,
NGC and IC target lookup is also fully offline. AAVSO catalog lookup, new HD
or free-text CDS name lookups, NASA ephemerides and place search need internet
at their first use; successful catalogue results are cached. A field already
prepared at home keeps its variables and comparison stars with no internet at
all. When the network is down, Argos serves the cached result and says so in
the log.

The status bar shows two quiet dots — `Seestar ●  Net ●` — so you always
know which of the two links is up.

Recommended order: try **scenario B** (phone hotspot) first — it covers
device control *and* live catalogs with zero extra hardware. Fall back to
**scenario A** (Seestar's own WiFi + offline cache) when the phone is not
available or its hotspot misbehaves. **Scenario C** needs a working USB
cable or Bluetooth PAN to the phone.

## Scenario A — Mac joined to the Seestar's own WiFi (fallback)

The Seestar out of the box runs its own access point (the network the iPad
joins). No home router, no phone involved.

1. On the Mac, join the `S30…`/`Seestar…` WiFi network.
2. In Argos, enter the Seestar's fixed IP address (`10.0.0.1`) and the
   Alpaca port (`32323`) on the Connection page.
3. Connect all. Capture, goto, focus and plate solving all work.

No internet: catalog lookups fall back to the offline cache (pre-fetch your
planned targets from home the day before — just solve a frame or run the
catalog query once while on the home network).

## Scenario B — everything on the phone's hotspot (recommended)

Both the Mac and the Seestar join the iPhone's *Partage de connexion*. This
gives the catalogs live internet, needs no cable, and is the recommended
field setup — one network for everything.

1. iPhone: enable the hotspot, and turn on **“Maximiser la compatibilité”**
   (forces 2.4 GHz, which the Seestar needs).
2. Seestar: in the Seestar app, switch the device to *station mode* and join
   the phone's hotspot (one-time setup).
3. Mac: join the same hotspot, then press **Discover** in Argos.
4. Phone hotspots usually block the Alpaca UDP
   broadcast, so Argos falls back to probing the last-used address and then
   sweeping the hotspot subnet (`172.20.10.x`) — the found IP address is
   kept for next time.

Caveats: the hotspot may pause when the phone sleeps, and the Seestar must
be re-pointed at the hotspot's SSID if you renamed it.

## Scenario C — best of both: Seestar WiFi + phone for internet

The Mac can hold two links at once: WiFi to the Seestar's AP, and internet
through the phone. Requires a working USB cable to the phone (or Bluetooth
PAN — slower but fine for catalog queries).

1. Join the Seestar's WiFi as in scenario A.
2. Plug the iPhone in over USB (or pair over Bluetooth) and enable the
   hotspot. macOS shows a new *iPhone USB* network service.
3. In **System Settings → Network**, make sure *iPhone USB* sits **above**
   *Wi-Fi* in the service order (⋯ menu → *Set Service Order…*). The default
   route (internet) then goes through the phone while the Seestar subnet
   stays on WiFi.
4. In Argos, use `10.0.0.1:32323`, then connect all. Both status dots go green.

## Address

Argos uses one clear endpoint: an **IP address** and an **Alpaca port**. The
last successful address is retained and is the first one tried by discovery.
For the Seestar access-point network that is normally `10.0.0.1:32323`; on a
home network or phone hotspot use **Discover** or enter the IP shown by your
router.

## Discovery, layer by layer

When you press **Discover**, Argos tries, in order:

1. the standard Alpaca UDP broadcast (port 32227);
2. direct HTTP probes of the last-used host, then `10.0.0.1` (AP mode);
3. a TCP sweep of the Mac's local /24 subnet, confirming candidates against
   the Alpaca management endpoint.

So discovery works even on networks that swallow broadcasts (phone
hotspots, isolated APs) — it just takes a few seconds longer.
