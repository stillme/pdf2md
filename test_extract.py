import pdfvault
import os

pdf_path = "sample.pdf"
output_md = "sample_with_figs.md"
fig_dir = "sample_figures"

print(f"Converting {pdf_path}...")
doc = pdfvault.convert(pdf_path, tier="fast", figures="extract")

print(f"Saving markdown to {output_md}...")
doc.save_markdown(output_md)

print(f"Saving figures to {fig_dir}...")
doc.save_figures(fig_dir)

print("Done!")
print(f"Number of figures found: {len(doc.figures)}")
for fig in doc.figures:
    print(f"  - {fig.id}: {fig.caption or 'No caption'} (Page {fig.page})")
