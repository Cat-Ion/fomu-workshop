#!/usr/bin/env python3
# This variable defines all the external programs that this module
# relies on.  lxbuildenv reads this variable in order to ensure
# the build will finish without exiting due to missing third-party
# programs.
LX_DEPENDENCIES = ["riscv", "icestorm"]

# Import lxbuildenv to integrate the deps/ directory
import lxbuildenv

# Disable pylint's E1101, which breaks completely on migen
#pylint:disable=E1101

from litex_boards.partner.platforms.fomu_evt import Platform
from litex_boards.partner.targets.fomu import _CRG

from litex.soc.integration import SoCCore
from litex.soc.integration.builder import Builder

from lxsocsupport import up5kspram

from valentyusb.usbcore import io as usbio
from valentyusb.usbcore.cpu import dummyusb

import argparse


class BaseSoC(SoCCore):
    SoCCore.csr_map = {
        "ctrl":           0,  # provided by default (optional)
        "crg":            1,  # user
        "uart_phy":       2,  # provided by default (optional)
        "uart":           3,  # provided by default (optional)
        "identifier_mem": 4,  # provided by default (optional)
        "timer0":         5,  # provided by default (optional)
        "cpu_or_bridge":  8,
        "usb":            9,
        "picorvspi":      10,
        "touch":          11,
        "reboot":         12,
        "rgb":            13,
        "version":        14,
    }

    def __init__(self, platform, output_dir="build",  placer=None, pnr_seed=0, use_pll=True, **kwargs):
        clk_freq = int(12e6)
        self.submodules.crg = _CRG(platform, use_pll=use_pll)
        SoCCore.__init__(self, platform, clk_freq,
                cpu_type=None,
                cpu_variant=None,
                integrated_sram_size=0,
                with_uart=False,
                with_ctrl=False,
                **kwargs)

        # UP5K has single port RAM, which is a dedicated 128 kilobyte block.
        # Use this as CPU RAM.
        spram_size = 128*1024
        self.submodules.spram = up5kspram.Up5kSPRAM(size=spram_size)
        self.register_mem("sram", 0x10000000, self.spram.bus, spram_size)

        # Add USB pads.  We use DummyUsb, which simply enumerates as a USB
        # device.  Then all interaction is done via the wishbone bridge.
        usb_pads = platform.request("usb")
        usb_iobuf = usbio.IoBuf(usb_pads.d_p, usb_pads.d_n, usb_pads.pullup)
        self.submodules.usb = dummyusb.DummyUsb(usb_iobuf, debug=True)
        self.add_wb_master(self.usb.debug_bridge.wishbone)

        # Add "-relut -dffe_min_ce_use 4" to the synth_ice40 command.
        # "-reult" adds an additional LUT pass to pack more stuff in, and
        # "-dffe_min_ce_use 4" flag prevents Yosys from generating a
        # Clock Enable signal for a LUT that has fewer than 4 flip-flops.
        # This increases density, and lets us use the FPGA more efficiently.
        platform.toolchain.nextpnr_yosys_template[2] += " -relut -dffe_min_ce_use 4"

        # Allow us to set the nextpnr seed, because some values don't meet timing.
        platform.toolchain.nextpnr_build_template[1] += " --seed " + str(pnr_seed)

        # Different placers can improve packing efficiency, however not all placers
        # are enabled on all builds of nextpnr-ice40.  Let the user override which
        # placer they want to use.
        if placer is not None:
            platform.toolchain.nextpnr_build_template[1] += " --placer {}".format(placer)

def main():
    parser = argparse.ArgumentParser(
        description="Build Fomu Main Gateware")
    parser.add_argument(
        "--seed", default=0, help="seed to use in nextpnr"
    )
    parser.add_argument(
        "--placer", choices=["sa", "heap"], help="which placer to use in nextpnr"
    )
    parser.add_argument(
        "--no-pll", help="disable pll -- this is easier to route, but may not work", action="store_true"
    )
    args = parser.parse_args()

    platform = Platform()
    soc = BaseSoC(platform, pnr_seed=args.seed, placer=args.placer, use_pll=not args.no_pll)
    builder = Builder(soc,
                      output_dir="build", csr_csv="test/csr.csv",
                      compile_software=False)
    vns = builder.build()
    soc.do_exit(vns)

if __name__ == "__main__":
    main()
