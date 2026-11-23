# The 3D office: trial findings and brief for Phase 4

**Status:** written after the P3.2 trial, 23 November 2026. Phase 4 (Document 06, Section 9) builds the full office from this brief.

## What the trial built

One floor of Data Operations, at `/games/<id>/office`, drawn with React Three Fiber:

* a desk for each member of staff, plus empty desks to show there is room to hire (at least six);
* people at their desks when working or free, and missing when away on a course or gone;
* paper piles on the desks for the open queue, shared across the desks in use, at most 12 sheets each;
* a server rack whose lights are green, or blink red while the systems are down;
* a meeting room standing for the monthly Data Quality Reviews.

Everything is drawn from one read-only endpoint, `GET /games/<id>/office/`, refreshed every two seconds. The scene follows the game without a page reload. The layout is a pure function (`frontend/src/lib/office.ts`) with its own unit tests, so what the floor shows is tested without WebGL. Clicking a desk, a person, the rack or the meeting room opens its 2D screen:

* a person at work: the work item they are on;
* other people and empty desks: Staff;
* the rack: IT;
* the meeting room: the Data Quality Reviews.

Below the scene, the same things are listed as links with a one-line summary, for keyboards, screen readers and computers without WebGL.

## Art style (proposed for Phase 4)

* **Low-poly, flat-shaded.** Boxes, six-sided cylinders and twenty-sided heads. No textures and no models to load: the whole floor is about 60 meshes.
* **Isometric orthographic camera** from the front right, zoomed to fit the floor in any window size.
* **Palette:**
  * floor and walls in the interface's slate greys;
  * desks in ochre and amber;
  * people at work in the brand teal (`#0f766e`), people free in slate;
  * status lights in green and red.
* **State is shown by what is there**, not by labels: who sits where, the size of the paper piles, the colour of the rack's lights. A hover label gives the words.

## Performance budget

Measured on the dev laptop in the Claude browser pane, 23 November 2026:

| Measure | Budget | Trial |
| --- | --- | --- |
| Frame rate, one floor | 60 frames a second | 120 (the display's limit) |
| JavaScript memory with the office open | +50 MB | +3 MB (49 → 52 MB) |
| Download for the rest of the game | unchanged | unchanged: 139 KB compressed |
| Download for the office | 300 KB compressed | 245 KB compressed (925 KB raw), only when the Office is opened |
| Data from the server | one small request every 2 s | one request every 2 s, a few hundred bytes |

## Findings for Phase 4

1. **Download size.** React Three Fiber registers the whole of three.js, so the office file carries all of it. Before the floors multiply, register only the classes used (R3F's `extend`), and measure again.
2. **People face the wrong way.** They stand by their chairs rather than sitting at their desks, facing the screen. Phase 4 needs seated and walking poses: a figure of a few parts, still low-poly.
3. **Where people are.** The trial knows only "at the desk" or "not here". The full office needs the meeting room, the training room and the coffee point to be places in the game's state, not decoration.
4. **The other departments.** Compliance, Sales and Finance have no floor yet. The three floors of Document 06 can follow the same pattern: an office endpoint per floor, a pure layout function, and a page that only draws.
5. **Lighting by time of day.** The game has a clock (08:00–17:00 working hours), so the office could darken after hours. This is cheap with one directional light.
6. **Low-spec machines.** The fallback message and the text list work without WebGL. A school's slowest laptop has not been tried. Phase 4 should test one and drop shadows or the device pixel ratio first if it struggles.
