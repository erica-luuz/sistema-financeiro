"""Configuração compartilhada pelos testes (o pytest lê este arquivo automaticamente).

Os testes não usam o .env de verdade: recebem uma SECRET_KEY própria, só para testar.
"""
import os

os.environ.setdefault("SECRET_KEY", "chave-somente-para-testes-" + "x" * 32)
