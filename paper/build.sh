#!/bin/bash
# LaTeX 编译脚本
# 用法: ./build.sh [clean]

cd "$(dirname "$0")"

module load latex/TexLive24 2>/dev/null

if [ "$1" = "clean" ]; then
    echo "Cleaning auxiliary files..."
    latexmk -C
    rm -f *.bbl *.run.xml *.synctex.gz
    echo "Done."
    exit 0
fi

echo "Compiling main.tex with XeLaTeX..."
latexmk -xelatex -interaction=nonstopmode -f main.tex

if [ -f main.pdf ]; then
    echo ""
    echo "✓ PDF generated: main.pdf ($(du -h main.pdf | cut -f1))"
else
    echo ""
    echo "✗ Compilation failed. Check main.log for errors."
fi
