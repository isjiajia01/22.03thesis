# Latexmk configuration to prevent auxiliary files in main directory
$pdf_mode = 5;  # Use xelatex
$out_dir = '.';  # Output directory (current directory)
$aux_dir = '.';  # Auxiliary directory (current directory)

# Enable SyncTeX for forward/inverse search
$xelatex = 'xelatex -synctex=1 -interaction=nonstopmode %O %S';

# Clean up auxiliary files
$clean_ext = 'aux bbl bcf blg fdb_latexmk fls log out run.xml toc xdv synctex.gz';
$clean_full_ext = 'aux bbl bcf blg fdb_latexmk fls log out run.xml toc xdv synctex.gz pdf';
