import os
import asyncio, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wallet_qa import W, newwallet, check, results, B
from playwright.async_api import async_playwright
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(**({'executable_path':os.environ['CHROME']} if os.environ.get('CHROME') else {}))
        w=await newwallet(b,'crash'); await w.create(); await w.add_mint(B); await w.receive_ln(100)
        # Simulate: wallet created an invoice (saved), the mint issued the ecash, but the app died before saving it.
        await w.ev(f"""(async()=>{{ const S=Nutcade.S; const ws=new CashuLib.Wallet('{B}',{{unit:'sat',bip39seed:CashuLib.mnemonicToSeedSync(S.seed.mnemonic),counterInit:{{...S.counters}}}}); await ws.loadMint();
            const q=await ws.createMintQuoteBolt11(640);
            const id='crash'+Date.now(); S.txs.unshift({{id,ts:Date.now(),note:'',status:'pending',fee:0,type:'in',method:'ln',amount:640,mint:'{B}',quote:q.quote,request:q.request}});
            S.quotes.push({{kind:'bolt11',quote:q.quote,request:q.request,amount:640,mint:'{B}',txId:id}});
            localStorage.setItem('nutcade:txs',JSON.stringify(S.txs)); localStorage.setItem('nutcade:quotes',JSON.stringify(S.quotes));
            await new Promise(r=>setTimeout(r,1200)); const ps=await ws.mintProofsBolt11(640,q.quote); window.__lost=ps.length; window.__q=q.quote; }})()""")
        q={'quote': await w.ev("window.__q")}
        check('setup: mint issued 640 sats the wallet never saved', await w.bal()==100 and await w.ev("window.__lost>0"))
        await w.pg.reload(); await w.until("Object.values(Nutcade.S.proofs).flat().reduce((t,p)=>t+p.amount,0)>=740", 20000)
        check('interrupted deposit recovered automatically on next open', await w.bal()==740, await w.bal())
        check('deposit marked done', await w.ev(f"Nutcade.S.txs.find(t=>t.quote==='{q['quote']}').status")=='done')
        check('no script errors (crash)', not w.errs, w.errs[:3])
        await b.close(); print('\nSUMMARY', sum(r[1] for r in results), '/', len(results))
asyncio.run(main()); sys.exit(0 if results and all(r[1] for r in results) else 1)
