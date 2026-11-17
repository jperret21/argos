# Install ARGOS

Three things have to be in place before your first night: ARGOS itself, the
ASTAP plate solver with a star database, and the link between them. Budget
twenty minutes indoors. None of it should be attempted in the dark.

```{admonition} ARGOS 0.5.0 is a beta
:class: warning

0.5.0 is the first beta of the new ARGOS: the interface now runs in a desktop
app for macOS and Linux, and the old PyQt6 application is retired. It was
tested with its built-in simulator and with replays of real nights recorded
with a Seestar S30 Pro. **It has not yet been used live on a telescope**:
treat your first night as a test night, and keep the Seestar app at hand.
What changed is in {doc}`release_0_5_0`.
```

```{admonition} What you do *not* need
:class: tip

You do not need Python. The macOS and Linux packages carry their own copy of
the ARGOS server. The `uv` and `npm` commands in {doc}`CONTRIBUTING` are for
people modifying the source, not for observers.
```

## 1. Install ARGOS

Downloads are on the [v0.5.0 release
page](https://github.com/jperret21/argos/releases/tag/v0.5.0).

`````{grid} 1 1 3 3
:gutter: 2

````{grid-item-card} macOS
`ARGOS-0.5.0-macOS-arm64.dmg`, Apple silicon.

Open the `.dmg` and drag **ARGOS** onto the **Applications** link beside it.
The image also holds `READ ME FIRST.txt` (the first-launch steps below) and
`LICENSE.txt`.
````

````{grid-item-card} Linux
`ARGOS_0.5.0_amd64.deb`, x86-64 Debian or Ubuntu.

```bash
sudo apt install ./ARGOS_0.5.0_amd64.deb
```

`apt` installs the libraries the package depends on, WebKitGTK 4.1 among
them; the ARGOS server comes inside the package. ARGOS then appears in the
applications menu. A technical preview: never used on a Linux desktop by the
project.
````

````{grid-item-card} Source
Tag `v0.5.0`, for developers.

```bash
uv sync --extra dev --extra qt --extra server
(cd web && npm install)
uv run python run_web.py --sim
```

Details in {doc}`CONTRIBUTING`.
````
`````

### First launch on macOS

The app is signed ad hoc, not with an Apple Developer certificate, and it is
not notarised, so macOS blocks it the first time. This is about the absence of
a paid certificate, not about the software being unsafe. You do this once:

1. Drag ARGOS into your Applications folder.
2. Open ARGOS once. macOS refuses it: click **Done**.
3. On **macOS 15 (Sequoia) or later**: open **System Settings › Privacy &
   Security**, scroll to the line "ARGOS was blocked to protect your Mac",
   click **Open Anyway**, then **Open Anyway** again in the dialog (your
   password may be asked).
   On **macOS 11 to 14**: right-click (or Control-click) ARGOS in
   Applications, choose **Open**, then **Open** again in the dialog.

Afterwards ARGOS opens normally. The very first launch can take longer while
macOS checks the application.

````{admonition} "ARGOS is damaged and can't be opened"
:class: warning

That is the quarantine attribute macOS puts on downloads, not a corrupt file.
Remove it in Terminal, then open ARGOS again:

```bash
xattr -dr com.apple.quarantine "/Applications/ARGOS.app"
```
````

### What your computer needs

| | macOS | Linux |
|---|---|---|
| Processor | Apple silicon (M1 or later). There is no Intel build. | x86-64 |
| System | macOS 11 (Big Sur) or later, the minimum the app declares. The window draws the interface with macOS's own WebKit, and the interface uses WebKit features of Safari 16.2: on macOS 11 and 12, install the Safari updates up to 16.2 or later. | A Debian or Ubuntu system with the WebKitGTK 4.1 library, which `apt` installs with the package. The package is built on Ubuntu 22.04, so it needs Ubuntu 22.04 or Debian 12 or later (glibc 2.35 or later, the highest version the 0.5.0 package's binaries ask for). |
| Tested | Built and run on a recent macOS (26) only; older versions down to 11 are allowed by the build but untested. | Built and its server smoke-tested by the release workflow; not yet installed and run on a Linux desktop. |
| Disk | Room for a night of frames in the sessions folder: plan on a few GB. | Same. |

ARGOS talks to the Seestar over Wi-Fi (ASCOM Alpaca). It does not need the
internet during the night: see {doc}`field_connectivity`.

## 2. Install ASTAP and a star database

ARGOS does not bundle a plate solver, and without one it cannot identify a
field, so it cannot do photometry. [ASTAP](https://www.hnsky.org/astap.htm) is
free.

**Two separate downloads, and you need both:**

1. the ASTAP program for your platform;
2. one **star database**.

```{admonition} Which database? D50.
:class: important

ASTAP publishes several, distinguished by star density rather than magnitude:
D05, D20, D50, D80 (general purpose), V50 (with Johnson-V magnitudes), G05
(galaxies) and W08 (very wide field).

Every Seestar profile has a field between 0.7° and 4.0° (the S50's 0.72° ×
1.28° to the S30 Pro's 2.24° × 3.99°), which lands in the range ASTAP solves
from the D-series. **D50 is the right default.** Take D20 if disk space is
tight; D80 is larger (about 1.25 GB) with no disadvantage but its size. Do not
take G05 or W08: they are for fields far outside this range.
```

## 3. Point ARGOS at ASTAP

Open **Settings › Plate solving** (**F5**, or **⌘,** on macOS and **Ctrl+,** on
Linux, then the category list).

- **ASTAP executable**: leave it empty if ASTAP is installed in the usual
  place. ARGOS looks for `astap_cli` or `astap` on the `PATH`, then in
  `/Applications/ASTAP.app`, the Homebrew folders, `/usr/local/bin`,
  `/usr/bin` and `/opt/astap`.
- **Database set**: choose **D50** (or the set you installed). **Auto** lets
  ASTAP pick one itself.
- **Star database folder**: leave it empty unless ARGOS does not find the
  database next to ASTAP or in the usual folders. A folder is passed with the
  chosen set: the page's **Solve flags** line shows both (`-D` and `-d`).

The ASTAP status on that page has to confirm **both** the program and the
star database. ARGOS cannot solve from the program alone, and the failure mode
if you get this wrong is a solve that simply never succeeds, at one in the
morning.

````{admonition} Typing a path instead of browsing
:class: warning

ARGOS's own file browser lists only your home folder and ARGOS's data
folders, so it cannot reach `/Applications` or `/opt`. To set a program
there, type the full path in the field and press **Enter**. On macOS, ASTAP
arrives as `ASTAP.app`, which is a folder; the program is inside it:

```text
/Applications/ASTAP.app/Contents/MacOS/astap
```
````

## 4. Check it before you rely on it

Do this indoors, in daylight, with no telescope connected:

- [ ] ARGOS opens on the **Connection** screen (**F1**).
- [ ] **Settings › Plate solving** confirms both the program and the star
      database.
- [ ] **Settings › Observer & site** has your observer name, your AAVSO
      observer code and your site.
- [ ] On **Connection**, the **Instrument** card names the telescope you own
      (it is chosen there, not in Settings).
- [ ] **Settings › Data & storage** points the **Sessions folder** at a disk
      with room for a night (the default is `~/Argos/sessions`).
- [ ] On **Observe** (**F2**), **Open FITS** (**⌘O**, **Ctrl+O** on Linux) on
      a raw frame from an earlier Seestar night, then the **Field** mode
      (**Alt+3**) and **Identify field** (**S**): the frame is identified.
      *This is the real test of steps 2 and 3.*

On a Mac keyboard the F-keys may need **Fn**; in the desktop app **⌘1** to
**⌘5** switch screens too.

To try the rest of ARGOS indoors, pick **Simulator** in the Connection
screen's **Link** card and press **Connect all**: a simulated mount, camera,
filter wheel and focuser answer, and **Take shot** saves real FITS files into
the sessions folder. Simulator frames are a synthetic star field that no
catalogue matches, so they cannot be plate-solved: the field test above needs a
real frame.

```{figure} ../docs/img/connection.webp
:loading: lazy
:alt: The ARGOS Connection screen with the simulator connected: four of four devices ready (mount, camera, filter wheel, focuser), the Seestar S30 Pro profile, the site check agreeing with the mount, and the Link card.

The Connection screen with the simulator as the link: the Instrument card
(profile and site), the Link card, the four devices ready and the Stellarium
bridge. Captured with a test configuration.
```

If you have no raw frame to hand, the first frame of your first session will
do, but then you are testing your solver setup in the field, which is the
thing this page exists to avoid.

```{seealso}
{doc}`guide`: the observing session itself, from settings to hand-off.
{doc}`field_connectivity`: getting the computer and the Seestar onto the same
network with no home router.
```
