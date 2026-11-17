# Identify a solved field

ARGOS separates **plate solving** from **catalogue identification**. This is
important: ASTAP first establishes a mapping between image pixels and sky
coordinates. Only then can ARGOS query, cache and project catalogue objects
onto the frame.

Field identification is an observing aid. It makes the contents of a frame
inspectable and lets the observer keep a target, comparison ensemble and check
star with the session. It does not turn a live frame into a calibrated
measurement or prove that every visible source has a catalogue identity.

## 1. Solve before assigning a role

With a full-resolution light frame on screen (a **Take shot**, or a raw frame
opened with **Open FITS**), switch Observe to the **Field** mode (**Alt+3**)
and press **Identify field** (**S**; press it again to cancel). ARGOS runs the
configured ASTAP program on the green plane and reads the solution back. The
chip on the image then gives the plate scale and the rotation, with a compass
and an arcminute scale bar. Check the solved centre, scale, rotation and
overlays against the image before selecting a target or comparison star.

```{figure} ../docs/img/observe-field.webp
:loading: lazy
:alt: ARGOS Observe in Field mode on a replayed frame of the RR Lyr field: the frame identified at 3.67″/px, RR Lyr circled, five comparison stars in squares and the check star 000-BCG-523 in a triangle among the VSX variables, with the comparison-candidates table below.

A frame of the RR Lyr field identified at 3.67″/px (the S30 Pro's nominal
scale is 3.74″/px): RR Lyr circled, five VSP comparison stars in squares, the
check star in a triangle, the VSX variables, and the comparison candidates in
the Field band. Captured from a replay of real frames (2026-09-25) through
ARGOS's simulator; Gaia DR3 was not reachable, so no Gaia layer is drawn.
```

If markers do not line up with stellar centroids, stop and solve that problem
first. Changing a display stretch, CFA preview or zoom must not be used to
"correct" a mismatch: those are display operations, while a solution error is
a coordinate error.

Within a session, ARGOS also guards against a wrong solution replacing a good
one: a solution whose plate scale is more than 1 % from the session's is
refused, and so is one that the stars ARGOS is tracking do not confirm. Three
solutions that agree with one another are accepted (the mount was re-pointed),
and the scale reference moves with them.

## 2. Control what is drawn

The **Catalogue layers** popover (**O**) is both the switchboard and the legend
of the overlay: each row shows the layer's mark and its count on this field.
Before a solve every row is unavailable.

| Object layer | What it draws |
|---|---|
| **Stars (Gaia DR3 + SIMBAD)** | [Gaia DR3](https://www.cosmos.esa.int/web/gaia/dr3) stars, with conventional [SIMBAD](https://simbad.cds.unistra.fr/) identities when available. |
| **Variables (VSX)** | Variable stars from the [AAVSO VSX](https://vsx.aavso.org/) catalogue; suspected ones dashed. |
| **Galaxies** | Galaxies identified by SIMBAD or the bundled Messier, NGC and IC catalogue. |
| **Nebulae + clusters** | Nebulae and star clusters from SIMBAD or the bundled Messier, NGC and IC catalogue. |
| **Exoplanet hosts** | Stars with confirmed exoplanets in the [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/), cache first. The marker identifies the host, not a resolved planet. |
| **Other objects** | Other SIMBAD sources, such as radio or X-ray sources. |

| Reference or display row | What it does |
|---|---|
| **VSP references, detected** | [AAVSO VSP](https://app.aavso.org/vsp/) comparison stars detected on the solved frame: candidates, not necessarily the ensemble you selected. The Field band under the image lists every VSP star of the frame. |
| **Selected stars** | The target (circle), the comparisons (squares) and the check star (triangle) of this observation. |
| **Coordinate grid** (**G**) | RA/Dec grid derived from the solved WCS. |
| **Labels** (**N**) | Compact labels that avoid each other. Keep them off in crowded fields and click a marker for its full identity. |

The **Gaia G limit** slider in the popover filters the stars drawn on the image
at once; it is a display depth, not a detection threshold. How deep ARGOS
fetches is set in **Settings › Catalogues** (**Gaia depth**), together with the
**Identification budget**, the number of online identities for one field. A
deeper limit returns many more objects, takes longer to identify a field and
makes labels unreadable. Start with a useful depth, then increase it only when a
source of interest is still missing.

Hiding a layer does not remove data from the session or alter the FITS. It
only changes what is displayed over the current image. Each mode remembers its
own layers.

```{admonition} Not every magnitude on screen is a photometric magnitude
:class: warning

The **Stars** layer shows Gaia $G$, a very broad white-light band, and *not*
$V$. It is there so you can tell a 12th-magnitude star from a 16th, and it is
excellent for that. It is not what builds the zero point.

Only the **VSP** stars carry sequence magnitudes calibrated by the AAVSO in a
standard band, with an AUID. That is why a manually clicked star can be kept
as a comparison and still contribute nothing to the ensemble: it has a
position and a flux, but no calibrated magnitude to difference against. See
the ensemble in {doc}`differential_photometry`.
```

## 3. Catalogue coverage and identity

ARGOS combines a bundled catalogue of Messier, NGC and IC objects with local
caches and optional network requests. The exact result depends on the solved
footprint, the selected layers, the depth, the identification budget and
whether the requested service has cached data for that field.

An uncircled star is not necessarily a failed detection. It may be fainter than
the selected limit, absent from the chosen catalogue, beyond the identification
budget, not returned by an optional service, or too close to another source for
a reliable projected match. Conversely, an annotated name is a catalogue
cross-match, not an assertion about photometric suitability.

Click a star for its card: its identity, and one line of facts (magnitude,
colour, distance from the target, catalogue). The **Inspector** card gives the
details, with a thumbnail of the star in its aperture. Long identifiers are
shortened in the overlay; the card is the place to read the full identity.

Catalogue requests are explicit. ARGOS can use the network for optional
lookups, but the resulting cache is local and can be inspected or cleared in
**Settings › Data & storage**. An offline session uses the bundled catalogue
and whatever matching entries have already been cached; it never uploads
frames or telemetry.

## 4. Select the photometry roles

Once the solution and markers are credible, click a star and give it a role
with the card's role buttons:

| Role | Purpose |
|---|---|
| **Target** | Science source whose differential signal is followed. |
| **Comparison** | Reference star contributing to the ensemble zero point. |
| **Check** | A star expected to remain constant, measured against the ensemble as a diagnostic. |

The **Field band** under the image lists the VSP comparison candidates with
their *V*, *B−V* and its difference from the target's, their distance from the
target against your limit, their peak and SNR on the solved frame, and the
Gaia sources that fall in their aperture. **Recommend…** on the Photometry card
proposes candidates that pass the pilot gate of **Settings › Photometry**
(SNR, magnitude range, distance). Treat this as a ranked starting point, not as
a scientific endorsement. Inspect saturation, isolation, brightness and colour;
the exact ensemble is recorded with the session (`targets/<object>.json`, and
the run folder's `targets.json`).

ARGOS names a comparison or check star that has a brighter star of the set
within two aperture radii, under the Field band's note line and in the log: the
brighter star's light reaches its aperture or its sky annulus. Nothing is
removed for you; prefer another star.

The same set is shown in the Photometry card, the Field band and the
**Selected stars** layer. A row picked in a table selects the star on the
image, so the table and the field never become two conflicting views of the
session. Every role change can be undone from the toast that follows it.

## 5. During a sequence

A sequence keeps the field identified as frames arrive. Its apertures follow
the stars from frame to frame, moved by a fit on up to six well-measured,
isolated comparison and check stars (the anchors), and each aperture also follows its star's proper motion where
Gaia DR3 gives one. A frame on which the anchors are not where the fit puts
them gets no point. A live curve or new overlay is an operational check: common
shifts can be caused by clouds, focus, tracking, saturation or a changing sky
background. In **Review**, select a suspicious point and press **Enter** to
open its source frame.

ARGOS does not calibrate raw lights with darks, flats or bias frames during this
quick-look identification and measurement. Keep all raw calibration frames and
perform the final calibrated reduction independently.

## 6. Troubleshooting

| Symptom | First check |
|---|---|
| Identify field never succeeds | **Settings › Plate solving** must confirm both the ASTAP program and the star database ({doc}`install`). |
| Marker is not centred on a star | Confirm ASTAP's centre, scale and rotation on a full-resolution frame. |
| A new solution is refused | Its scale is more than 1 % from the session's, or the tracked stars do not confirm it: the log says which. |
| Needed source is absent | Check the layer, the Gaia limit and the identification budget, then the cache and the network. |
| Labels fill the frame | Hide labels (**N**), lower the Gaia limit or hide layers; click individual markers instead. |
| Too few comparison candidates | Confirm the solve and the pilot gate in **Settings › Photometry**, then select candidates by hand and record why for the final reduction. |
| Same object has several names | Use the card's full identity and coordinates; overlay labels are abbreviated on purpose. |

```{seealso}
- {doc}`guide`: the observer-oriented version of this workflow, in the order
  you actually do it.
- {doc}`differential_photometry`: what happens to a star once you have given
  it a role.
- {doc}`references`: every catalogue named on this page, with its citation and
  its acknowledgement requirements.
```
