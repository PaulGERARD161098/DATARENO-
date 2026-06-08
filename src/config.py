"""config — chargement .env, constantes de segmentation, garde-fous.

Placeholder (à implémenter en Phase 1). Doit porter, à terme :
- chargement des variables d'environnement (secrets jamais en dur) ;
- mapping chauffage → segment :
  GAZ/FIOUL → AIR_EAU · ÉLEC → AIR_AIR · BOIS → AIR_EAU_A_QUALIFIER · déjà-PAC/inconnu → EXCLU ;
- listes de claims interdits (« 1€ », « -X% » non sourcé, « installation 48h »).
"""
