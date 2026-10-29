#!/usr/bin/env python3
"""Compatibility notice: the retired FAL image-generation CLI never submits requests."""
import argparse
parser=argparse.ArgumentParser(description="FAL generation is retired. Use the host built-in image_gen/image_generation tool following pptx-gen/REFERENCE.md. Assemble complete images with images_to_pptx.py.")
parser.parse_known_args()
parser.exit(2, "Retired backend: no image or network request was made. Read pptx-gen/references/slide-image-workflow.md and use the host image tool.\n")
