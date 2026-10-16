# HydroTeam V0 livery (Assetto Corsa)

Builds `autopilot/skins/gtp_radical_rxc_gt3/hydroteam_v0/body.dds` — the
HydroTeam V0 livery for the `gtp_radical_rxc_gt3` car — on top of that car's
`HT_Themed` skin (colours + stripes), with the number 56, HydroTeam, KU Leuven
and partner logos (from the HydroTeam design system, whitened like on the real
car). The autopilot installs the skin into AC and uses it automatically.

Needs a copy of the car folder next to the scripts (`car/`, from
`assettocorsa/content/cars/gtp_radical_rxc_gt3`).

    python compose.py                      # -> hydroteam_body.png
    python write_dds.py hydroteam_body.png body.dds   # DXT5 + mipmaps
    python render.py hydroteam_body.png check.jpg     # 3D check from the .kn5

UV zones and text orientation were measured on the `00_Skittles` skin: on the
sides text runs along the texture's y axis (left side rotated -90°, right
side +90°, mirrored x), on the hood and the sun strip it is rotated 180°.
`ht_body_dds.png` is `car/skins/HT_Themed/body.dds` saved as PNG.
