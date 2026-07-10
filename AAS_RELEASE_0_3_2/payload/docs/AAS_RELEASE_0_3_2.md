# AAS release 0.3.2

## Added elements
Al, Ag, Zn, Cu, Ni, Co.

## Engine
All six elements use the shared RTF clone engine:
- `MGA_STANDARD.rtf` is the layout source;
- the element DOCX supplies the instrument chart;
- the JSON file supplies calculation parameters;
- measurement rows are created dynamically for 2–5 parallels.

## Timestamp rule
Each parallel measurement has its own `row_N.action_time`.
Intervals are deterministically generated in the range 9:00–10:00 minutes.
The report header uses the latest measurement time.

## Supported AAS elements
Ag, Al, As, Ba, Cd, Co, Cr, Cu, Fe, Hg, Mn, Ni, Pb, Sb, Se, Sn, Ti, Zn.
