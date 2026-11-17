# Field connectivity guide

How to connect the computer running ARGOS to the Seestar away from the home
network, and what still works (or not) without internet.

## What actually needs what

| Feature | Needs the Seestar | Needs internet |
|---|---|---|
| Mount, camera, focuser and filter wheel control, including the jog (ASCOM Alpaca, port 32323) | yes | no |
| Plate solving (ASTAP, local star database) | no | **no** |
| Stellarium telescope control (local bridge) | no | no |
| Messier, NGC and IC target names | no: **built in** | no |
| AAVSO VSX and VSP catalogues (variables, comparison stars) | no | yes: **cached** |
| Gaia DR3, SIMBAD and NASA Exoplanet Archive lookups | no | yes: **cached** |
| Site search (**Find a place**) | no | yes |

Plate solving is fully offline: ASTAP and its database live on the computer.
Messier, NGC and IC target lookup is also fully offline. AAVSO catalogue
lookup, other name lookups through CDS, NASA ephemerides and the site search
need internet at their first use; successful catalogue results are cached. A
field already prepared at home keeps its variables and comparison stars with
no internet at all. When the network is down, ARGOS serves the cached result
and says so in the log.

The status bar shows a **Seestar** and a **Net** mark. ARGOS checks the
Seestar every 10 s; it never probes the internet in the background, so the
**Net** mark reflects the last check you asked for (the "check now" button
next to it on the Connection screen's **Link** card).

```{tip}
**Try scenario B first**: the phone hotspot covers device control *and* live
catalogues with no extra hardware. Fall back to **scenario A** (the Seestar's
own Wi-Fi plus the offline cache) when the phone is unavailable or its hotspot
misbehaves. **Scenario C** needs a Mac and a working USB cable or Bluetooth
PAN to the phone.
```

## Scenario A: computer joined to the Seestar's own Wi-Fi (fallback)

The Seestar out of the box runs its own access point (the network the phone or
tablet joins). No home router, no phone involved.

1. On the computer, join the `S30…`/`Seestar…` Wi-Fi network.
2. In ARGOS, on the Connection screen's **Link** card, choose **Seestar
   (Alpaca)**, with the address `10.0.0.1` and the Alpaca port `32323`.
3. **Connect all**. Capture, GoTo, focus and plate solving all work.

No internet: catalogue lookups fall back to the offline cache. Pre-fetch your
planned targets from home the day before: identify a frame of the field, or
search the target in **Plan**, once while on the home network.

## Scenario B: everything on the phone's hotspot (recommended)

Both the computer and the Seestar join the phone's **Personal Hotspot**. This
gives the catalogues live internet, needs no cable, and is the recommended
field set-up: one network for everything.

1. iPhone: enable the hotspot, and turn on **Maximise Compatibility** (it
   forces 2.4 GHz, which the Seestar needs).
2. Seestar: in the Seestar app, switch the device to *station mode* and join
   the phone's hotspot (one-time set-up).
3. Computer: join the same hotspot, then press **Discover** on the **Link**
   card. When several devices answer, ARGOS asks which one; **Cancel** stops
   the search.
4. Phone hotspots usually block the Alpaca UDP broadcast, so ARGOS falls back
   to probing the last-used address and then sweeping the hotspot's subnet
   (`172.20.10.x` on an iPhone). The address found is kept for next time.

Caveats: the hotspot may pause when the phone sleeps, and the Seestar must be
re-pointed at the hotspot's network name if you renamed it.

## Scenario C: best of both, Seestar Wi-Fi plus the phone for internet (Mac)

The Mac can hold two links at once: Wi-Fi to the Seestar's access point, and
internet through the phone. This needs a working USB cable to the phone (or
Bluetooth PAN, slower but fine for catalogue queries).

1. Join the Seestar's Wi-Fi as in scenario A.
2. Plug the iPhone in over USB (or pair over Bluetooth) and enable the
   hotspot. macOS shows a new *iPhone USB* network service.
3. In **System Settings › Network**, make sure *iPhone USB* sits **above**
   *Wi-Fi* in the service order (⋯ menu › *Set Service Order…*). The default
   route (internet) then goes through the phone while the Seestar's subnet
   stays on Wi-Fi.
4. In ARGOS, use `10.0.0.1` and port `32323`, then **Connect all**. Check both
   marks on the Link card: the Seestar is reachable, and **check now** finds
   the internet.

## Address

ARGOS uses one endpoint: the **Seestar address** and the **Alpaca port**
(on the Connection screen's **Link** card; a typed value is saved when you
press Enter or leave the field). The last address that worked is kept, and is tried as soon
as the UDP broadcast comes back empty (see the discovery order below). On the
Seestar's access-point network it is normally `10.0.0.1:32323`; on a home
network or phone hotspot use **Discover** or enter the address shown by your
router.

## Discovery, layer by layer

When you press **Discover**, ARGOS tries, in order:

1. the standard [Alpaca UDP discovery](https://ascom-standards.org/api/)
   broadcast (port 32227);
2. direct HTTP probes of the last-used address, then `10.0.0.1` (the
   access-point address);
3. a TCP sweep of the computer's local /24 subnet, confirming candidates
   against the Alpaca management endpoint.

So discovery works even on networks that swallow broadcasts (phone hotspots,
isolated access points); it just takes a few seconds longer.

```{seealso}
{doc}`guide` for the connection step in context, and {doc}`seestar_protocol`
for what is on each port.
```
