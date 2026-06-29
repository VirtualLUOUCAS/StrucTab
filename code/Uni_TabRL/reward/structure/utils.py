"""Helper functions for the 1D Probe structural reward."""

from bs4 import BeautifulSoup, NavigableString


def clean_table_content(html_str: str) -> str:
    """Strip all text inside ``td`` / ``th`` cells, keeping tags and attributes."""
    soup = BeautifulSoup(html_str, "html.parser")

    for cell in soup.find_all(["td", "th"]):
        cell.clear()

    # Remove stray text nodes directly under <tr>.
    for tr in soup.find_all("tr"):
        for content in list(tr.contents):
            if isinstance(content, NavigableString):
                content.extract()

    return str(soup)


def extract_cells_with_row(soup: BeautifulSoup) -> list[tuple[BeautifulSoup, int]]:
    """Return ``[(cell, row_index), ...]`` in row-by-row, left-to-right order."""
    cells_with_row = []
    for row_idx, row in enumerate(soup.find_all("tr")):
        for cell in row.find_all(["td", "th"]):
            cells_with_row.append((cell, row_idx))
    return cells_with_row


def cells_match(cell1: BeautifulSoup, row1: int, cell2: BeautifulSoup, row2: int) -> bool:
    """Two cells match iff same row index, same tag name and same attributes."""
    if row1 != row2:
        return False
    if cell1.name != cell2.name:
        return False
    if dict(cell1.attrs) != dict(cell2.attrs):
        return False
    return True
