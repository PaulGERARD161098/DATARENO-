"""tri — Phase 1 : segmentation de la base par mode de chauffage.

Placeholder (à implémenter). CLI cible :
    python -m src.tri data/base.csv --outdir out

Sorties attendues :
- out/segments/*.csv      (un fichier par segment, priorité surface ↑)
- out/_isoles_qualite.csv (lignes invalides isolées + raison, jamais droppées)
- out/synthese.xlsx       (comptes par segment)

Exclusions : déjà-PAC / inconnu → EXCLU ; « Tel seul » exclus du canal.
"""
