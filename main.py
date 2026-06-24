#!/usr/bin/env python3
"""P.H.I. — Personal Home Inventory. Local desktop pantry tracker."""

from phi.ui.bootstrap import bootstrap_customtkinter_fonts

bootstrap_customtkinter_fonts()

from phi.app import run  # noqa: E402

if __name__ == "__main__":
    run()
