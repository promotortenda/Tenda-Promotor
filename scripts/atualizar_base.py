import json
import os
import time
from datetime import datetime, timezone, timedelta
import urllib.request
import urllib.parse

CEP_ALVO = "13255280"
CEP_FORMATADO = "13255-280"
LOJA_NOME = "Itatiba"
ARQUIVO_SAIDA = os.path.join("data", "produtos.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9",
}


def buscar_produtos_tenda(cep: str):
    """
    Consulta endpoints públicos de catálogo/vitrine associados ao CEP informado.
    Retorna lista padronizada no formato esperado pelo Index.html.
    """
    produtos_coletados = []
    vistos = set()

    termos_busca = [
        "arroz", "feijao", "cafe", "oleo", "acucar", "leite",
        "macarrao", "biscoito", "chocolate", "refrigerante", "cerveja",
        "sabao", "amaciante", "papel higienico", "frango", "carne",
        "queijo", "margarina", "iogurte", "molho"
    ]

    for termo in termos_busca:
        query = urllib.parse.quote(termo)
        url = f"https://api.tendaatacado.com.br/api/public/store/search?q={query}&zipCode={cep}&page=1&limit=50"
        req = urllib.request.Request(url, headers=HEADERS)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status != 200:
                    continue
                payload = json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            print(f"[Aviso] Falha ao consultar termo '{termo}': {e}")
            time.sleep(1.5)
            continue

        itens = []
        if isinstance(payload, dict):
            itens = payload.get("products") or payload.get("items") or payload.get("data") or []
        elif isinstance(payload, list):
            itens = payload

        for item in itens:
            ean = str(item.get("ean") or item.get("barcode") or item.get("gtin") or "").strip()
            nome = str(item.get("name") or item.get("title") or "").strip()
            if not nome:
                continue

            chave = ean if ean else nome.lower()
            if chave in vistos:
                continue
            vistos.add(chave)

            preco_comum = float(item.get("price") or item.get("regularPrice") or item.get("listPrice") or 0)
            preco_cartao = float(
                item.get("cardPrice")
                or item.get("tendaCardPrice")
                or item.get("promotionalPrice")
                or preco_comum
            )
            regra = str(item.get("promotionLabel") or item.get("badge") or "").strip()

            if preco_comum > 0:
                produtos_coletados.append({
                    "id": len(produtos_coletados) + 1,
                    "ean": ean,
                    "nome": nome,
                    "comum": round(preco_comum, 2),
                    "cartao": round(preco_cartao if preco_cartao > 0 else preco_comum, 2),
                    "regra": regra
                })

        time.sleep(1.2)

    return produtos_coletados


def main():
    os.makedirs("data", exist_ok=True)
    fuso_br = timezone(timedelta(hours=-3))
    agora = datetime.now(fuso_br).isoformat(timespec="seconds")

    print(f"Iniciando coleta para Loja {LOJA_NOME} (CEP {CEP_FORMATADO})...")
    produtos = buscar_produtos_tenda(CEP_ALVO)

    if not produtos:
        print("Nenhum produto retornado na coleta. Mantendo base anterior intacta.")
        return

    saida = {
        "atualizadoEm": agora,
        "loja": LOJA_NOME,
        "cep": CEP_FORMATADO,
        "total": len(produtos),
        "produtos": produtos
    }

    with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)

    print(f"Sucesso! {len(produtos)} produtos salvos em {ARQUIVO_SAIDA}.")


if __name__ == "__main__":
    main()
