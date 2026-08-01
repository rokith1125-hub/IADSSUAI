from typing import List, Dict

class ProfitCalculator:
    def calculate(self, markets: List[Dict], quantity: float, transport_cost: float) -> Dict:
        if not markets or quantity <= 0:
            return {"best_mandi": None, "net_profit": 0, "difference": 0, "table": []}

        table = []
        for item in markets:
            price = item.get('modal_price')
            if price is None:
                continue
            try:
                gross = float(price) * quantity
                transport = transport_cost * quantity
                net = gross - transport
            except Exception:
                continue
            table.append({
                "market": item.get('market'),
                "price": price,
                "net": round(net, 2)
            })

        if not table:
            return {"best_mandi": None, "net_profit": 0, "difference": 0, "table": []}

        table.sort(key=lambda x: x['net'], reverse=True)
        best = table[0]
        current = table[-1]
        return {
            "best_mandi": best['market'],
            "net_profit": best['net'],
            "difference": round(best['net'] - current['net'], 2),
            "table": table
        }
