//+------------------------------------------------------------------+
//|                                              BIST_Grid.mq5        |
//|  KANITLANMIŞ BIST GRID + TREND — her rejimde aktif, long-only     |
//|  YATAY (ER<0.30)→grid · YUKARI TREND→long · AŞAĞI TREND→nakit      |
//|  ÇOKLU SEMBOL: tüm Market Watch'ı tarar (InpScanAll).             |
//|  Kaufman ER<0.30 = yatay → grid; trend → kapat. Seviye -1/-2/-3%. |
//|  Birim +%1.5'te trailing aktif, peak'in %0.5 altına inince sat.   |
//|  💰 KASA KORUMA: öz sermayenin %20'si HER ZAMAN güvende (GLOBAL) —|
//|     tüm sembollerdeki toplam notional ≤ %80. Kaldıraç YOK. DEMO.  |
//+------------------------------------------------------------------+
#property copyright "OTT Bot — QUANT DESK"
#property version   "4.00"
#property strict
#include <Trade/Trade.mqh>

//============================ GİRDİLER ==============================
input bool    InpScanAll          = true;     // TÜM Market Watch sembollerini tara
input string  InpSymbols          = "GARAN,THYAO,ASELS,EREGL,SISE,KCHOL,AKBNK,SASA,TUPRS,FROTO"; // ScanAll=false ise
input ENUM_TIMEFRAMES InpTF        = PERIOD_H1; // Zaman dilimi (sistem H1)
input int     InpER_Win           = 20;      // Kaufman ER penceresi
input double  InpER_Th            = 0.30;     // ER < bu = YATAY (grid açık)
input double  InpLevel1Pct        = 1.0;      // 1. AL seviyesi: SMA20 -% (BIST sıkı)
input double  InpLevel2Pct        = 2.0;      // 2. AL seviyesi
input double  InpLevel3Pct        = 3.0;      // 3. AL seviyesi
input double  InpTakePct          = 1.5;      // +%X'te TRAILING aktifleş
input double  InpTrailPct         = 0.5;      // peak'in %X altına inince sat
input double  InpUnitPct          = 10.0;     // Birim başı = kasanın %X'i ile alabileceği kadar (yetmezse hisseyi atla)
input bool    InpTrendLong        = true;     // TREND'de boş durma: yukarı trend (fiyat>SMA) → long tut
input bool    InpAllowShort       = false;    // SHORT (demo): tepeden sat grid + aşağı trend short (BIST drift'i aleyhe — PF düşer)
input double  InpSafeReservePct   = 20.0;     // 💰 %X HER ZAMAN güvende (GLOBAL) → toplam ≤ %80
input long    InpMagic            = 20260103;
input int     InpTimerSec         = 10;       // Tarama aralığı (sn)
input bool    InpVerbose          = true;

//============================ GLOBAL ===============================
CTrade    trade;
string    g_symbols[];
datetime  g_lastBar[];
double    g_levels[3];

//+------------------------------------------------------------------+
int OnInit()
{
   int n = 0;
   if(InpScanAll)
   {
      int tot = SymbolsTotal(true);
      ArrayResize(g_symbols, tot);
      for(int i=0;i<tot;i++) g_symbols[i] = SymbolName(i, true);
      n = tot;
   }
   else n = StringSplit(InpSymbols, ',', g_symbols);
   if(n <= 0){ Print("HATA: taranacak sembol yok."); return INIT_FAILED; }

   ArrayResize(g_lastBar, n);
   for(int i=0;i<n;i++)
   {
      StringTrimLeft(g_symbols[i]); StringTrimRight(g_symbols[i]);
      SymbolSelect(g_symbols[i], true);
      g_lastBar[i] = 0;
   }
   g_levels[0]=InpLevel1Pct; g_levels[1]=InpLevel2Pct; g_levels[2]=InpLevel3Pct;
   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints(30);
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   PrintFormat("BIST GRID (çoklu) başladı · %d sembol · TF=%s · ER<%.2f · AL -%.0f/-%.0f/-%.0f%% · trailing +%.1f/%.1f%% · birim %%%.0f · KASA %.0f (%%%.0f güvende → max %%%.0f)",
               n, EnumToString(InpTF), InpER_Th, InpLevel1Pct, InpLevel2Pct, InpLevel3Pct,
               InpTakePct, InpTrailPct, InpUnitPct, eq, InpSafeReservePct, 100.0-InpSafeReservePct);
   EventSetTimer(MathMax(2, InpTimerSec));
   return INIT_SUCCEEDED;
}
void OnDeinit(const int reason){ EventKillTimer(); }
void OnTick(){ }   // ana mantık OnTimer'da (çoklu sembol)

//+------------------------------------------------------------------+
bool GetRegime(string sym, double &er, double &center)
{
   int need = InpER_Win + 2;
   double cl[]; ArraySetAsSeries(cl, false);
   if(CopyClose(sym, InpTF, 0, need, cl) < need) return false;
   int last = need - 2;
   double net = MathAbs(cl[last] - cl[last - InpER_Win]);
   double vol = 0;
   for(int i=last-InpER_Win+1; i<=last; i++) vol += MathAbs(cl[i]-cl[i-1]);
   er = (vol > 0) ? net/vol : 1.0;
   double sum = 0; for(int i=last-InpER_Win+1; i<=last; i++) sum += cl[i];
   center = sum / InpER_Win;
   return true;
}

//+------------------------------------------------------------------+
//| GLOBAL kasa koruma: tüm sembollerdeki magic notional toplamı     |
//+------------------------------------------------------------------+
double TotalNotional()
{
   double tot = 0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetInteger(POSITION_MAGIC) != InpMagic) continue;
      string s = PositionGetString(POSITION_SYMBOL);
      tot += PositionGetDouble(POSITION_VOLUME) * PositionGetDouble(POSITION_PRICE_CURRENT)
             * SymbolInfoDouble(s, SYMBOL_TRADE_CONTRACT_SIZE);
   }
   return tot;
}

bool LevelHeld(string sym, string prefix, int k)
{
   string tag = prefix + IntegerToString(k);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym &&
         PositionGetInteger(POSITION_MAGIC)==InpMagic &&
         PositionGetString(POSITION_COMMENT)==tag) return true;
   }
   return false;
}

// Yorum öneki: "G" = grid birimi, "T" = trend-long
bool HasTag(string sym, string prefix)
{
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         if(StringFind(PositionGetString(POSITION_COMMENT), prefix)==0) return true;
   }
   return false;
}

void CloseTag(string sym, string prefix, string why)
{
   int closed=0;
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk && PositionGetString(POSITION_SYMBOL)==sym && PositionGetInteger(POSITION_MAGIC)==InpMagic)
         if(StringFind(PositionGetString(POSITION_COMMENT), prefix)==0)
            { if(trade.PositionClose(tk)) closed++; }
   }
   if(InpVerbose && closed>0) PrintFormat("Kapatıldı (%s %s): %d · %s", sym, prefix, closed, why);
}

//+------------------------------------------------------------------+
double CalcLots(string sym, double ask)
{
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double usable = eq * (100.0 - InpSafeReservePct) / 100.0;     // %80 GLOBAL
   double budget = usable - TotalNotional();                     // kalan global bütçe
   if(budget <= 0) return 0;                                     // kasa korumalı: dur
   double target = MathMin(eq * InpUnitPct/100.0, budget);       // birim = %5 eq, bütçeyle sınırlı
   double cs = SymbolInfoDouble(sym, SYMBOL_TRADE_CONTRACT_SIZE);
   if(cs<=0 || ask<=0) return 0;
   double step = SymbolInfoDouble(sym, SYMBOL_VOLUME_STEP);
   double minl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MIN);
   double maxl = SymbolInfoDouble(sym, SYMBOL_VOLUME_MAX);
   if(step<=0) step=minl;
   double lots = MathFloor((target/(ask*cs))/step)*step;
   if(lots < minl) return 0;   // %10 bütçe 1 kontrata yetmiyor (pahalı hisse) → ATLA (konsantre olma)
   if(lots > maxl) lots = maxl;
   double need=0;
   if(OrderCalcMargin(ORDER_TYPE_BUY, sym, lots, ask, need))
      if(need > AccountInfoDouble(ACCOUNT_MARGIN_FREE)*0.98) return 0;
   int vd = (step>=1.0)?0:(int)MathRound(-MathLog10(step));
   return NormalizeDouble(lots, vd);
}

//+------------------------------------------------------------------+
void TrailSym(string sym)
{
   double bid = SymbolInfoDouble(sym, SYMBOL_BID);
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(StringFind(PositionGetString(POSITION_COMMENT),"G")!=0) continue;  // sadece GRID birimleri trail
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      if((bid-entry)/entry < InpTakePct/100.0) continue;          // +%1.5'e ulaşmadı
      double desiredSL = bid * (1.0 - InpTrailPct/100.0);
      double curSL = PositionGetDouble(POSITION_SL);
      if(curSL==0 || desiredSL > curSL)
         trade.PositionModify(tk, NormalizeDouble(desiredSL, dg), PositionGetDouble(POSITION_TP));
   }
}

// SHORT grid trailing: kâr +%1.5'e ulaşınca SL fiyatın üstüne, fiyat düştükçe aşağı çek
void TrailShort(string sym)
{
   double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
   int dg = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
   for(int i=PositionsTotal()-1; i>=0; i--)
   {
      ulong tk = PositionGetTicket(i);
      if(tk==0 || !PositionSelectByTicket(tk)) continue;
      if(PositionGetString(POSITION_SYMBOL)!=sym || PositionGetInteger(POSITION_MAGIC)!=InpMagic) continue;
      if(StringFind(PositionGetString(POSITION_COMMENT),"S")!=0) continue;  // sadece SHORT grid
      double entry = PositionGetDouble(POSITION_PRICE_OPEN);
      if((entry-ask)/entry < InpTakePct/100.0) continue;          // henüz +%1.5 kâr yok
      double desiredSL = ask * (1.0 + InpTrailPct/100.0);
      double curSL = PositionGetDouble(POSITION_SL);
      if(curSL==0 || desiredSL < curSL)                           // short: SL'i AŞAĞI çek
         trade.PositionModify(tk, NormalizeDouble(desiredSL, dg), PositionGetDouble(POSITION_TP));
   }
}

//+------------------------------------------------------------------+
void OnTimer()
{
   int n = ArraySize(g_symbols);
   int nSide=0, nUp=0, nDown=0, nUpAfford=0, nSideAfford=0, nSideDip=0, nData=0;  // tanı sayaçları
   for(int s=0; s<n; s++)
   {
      string sym = g_symbols[s];
      double er, center;
      if(!GetRegime(sym, er, center)) continue;
      nData++;
      bool sideways = (er < InpER_Th);
      datetime bt = iTime(sym, InpTF, 0);
      if(bt==0) continue;
      bool newbar = (bt != g_lastBar[s]);
      double bid = SymbolInfoDouble(sym, SYMBOL_BID);
      double ask = SymbolInfoDouble(sym, SYMBOL_ASK);
      // ── tanı: rejim + bütçe uygunluğu say
      {
         double eq0=AccountInfoDouble(ACCOUNT_EQUITY);
         double cs0=SymbolInfoDouble(sym,SYMBOL_TRADE_CONTRACT_SIZE);
         double ml0=SymbolInfoDouble(sym,SYMBOL_VOLUME_MIN);
         bool afford=(ask>0 && cs0>0 && ml0*ask*cs0 <= eq0*InpUnitPct/100.0);
         if(sideways)
         {
            nSide++;
            if(afford) nSideAfford++;
            if(afford && ask <= center*(1.0-g_levels[0]/100.0)) nSideDip++;  // uygun + ilk seviyede (dip)
         }
         else if(bid>center){ nUp++; if(afford) nUpAfford++; }
         else nDown++;
      }

      // ════════ TREND (ER ≥ eşik) ════════
      if(!sideways)
      {
         if(newbar)
         {
            if(HasTag(sym,"G")) CloseTag(sym,"G", StringFormat("TREND (ER=%.2f)", er));  // long grid kapat
            if(HasTag(sym,"S")) CloseTag(sym,"S", StringFormat("TREND (ER=%.2f)", er));  // short grid kapat
            bool up = (bid > center);                             // yön: fiyat>SMA = yukarı
            // YUKARI trend → trend-long
            if(InpTrendLong && ask>0 && up && !HasTag(sym,"T"))
            {
               double lots = CalcLots(sym, ask);
               if(lots>0 && trade.Buy(lots, sym, ask, 0, 0, "T"))
                  if(InpVerbose) PrintFormat("TREND-LONG AL: %s @ %.4g · %.2f lot (ER=%.2f yukarı)", sym, ask, lots, er);
            }
            if(up && HasTag(sym,"D")) CloseTag(sym,"D","yukarı döndü");   // short kapat
            // AŞAĞI trend → trend-short (sadece demo/AllowShort)
            if(InpAllowShort && bid>0 && !up && !HasTag(sym,"D"))
            {
               double lots = CalcLots(sym, bid);
               if(lots>0 && trade.Sell(lots, sym, bid, 0, 0, "D"))
                  if(InpVerbose) PrintFormat("TREND-SHORT SAT: %s @ %.4g · %.2f lot (ER=%.2f aşağı)", sym, bid, lots, er);
            }
            if(!up && HasTag(sym,"T")) CloseTag(sym,"T","aşağı trend"); // long kapat
            if(!InpTrendLong && HasTag(sym,"T")) CloseTag(sym,"T","trend-long kapalı");
            if(!InpAllowShort && HasTag(sym,"D")) CloseTag(sym,"D","short kapalı");
         }
         g_lastBar[s] = bt;
         continue;
      }

      // ════════ YATAY (ER < eşik) → GRID ════════
      if(HasTag(sym,"T")) CloseTag(sym,"T","yataya döndü");       // trend bitti → trend pozisyonları kapat
      if(HasTag(sym,"D")) CloseTag(sym,"D","yataya döndü");
      TrailSym(sym); TrailShort(sym);                            // grid birimlerini trailing'le yönet
      if(ask<=0){ g_lastBar[s]=bt; continue; }
      for(int k=0;k<3;k++)
      {
         // LONG grid: merkez altı seviyeye inince al
         double lvlL = center * (1.0 - g_levels[k]/100.0);
         if(ask <= lvlL && !LevelHeld(sym, "G", k+1))
         {
            double lots = CalcLots(sym, ask);
            if(lots > 0 && trade.Buy(lots, sym, ask, 0, 0, "G"+IntegerToString(k+1)))
               if(InpVerbose){ double eq=AccountInfoDouble(ACCOUNT_EQUITY);
                  PrintFormat("GRID AL: %s sev%d @ %.4g · %.2f lot · kasa %%%.0f", sym, k+1, ask, lots, TotalNotional()/eq*100.0); }
         }
         // SHORT grid: merkez üstü seviyeye çıkınca sat (demo/AllowShort)
         if(InpAllowShort)
         {
            double lvlS = center * (1.0 + g_levels[k]/100.0);
            if(bid >= lvlS && !LevelHeld(sym, "S", k+1))
            {
               double lots = CalcLots(sym, bid);
               if(lots > 0 && trade.Sell(lots, sym, bid, 0, 0, "S"+IntegerToString(k+1)))
                  if(InpVerbose) PrintFormat("GRID SAT (short): %s sev%d @ %.4g · %.2f lot", sym, k+1, bid, lots);
            }
         }
      }
      g_lastBar[s] = bt;
      Sleep(5);
   }
   // ── TANI ÖZETİ (30 sn'de bir) — neden işlem açıldı/açılmadı
   static datetime lastDiag = 0;
   if(TimeCurrent() - lastDiag >= 30)
   {
      lastDiag = TimeCurrent();
      double eq=AccountInfoDouble(ACCOUNT_EQUITY);
      PrintFormat("TANI: veri %d · 🟦yatay %d (uygun %d, DİP'te %d) · 📈yukarı %d (uygun %d) · 📉aşağı %d · açık %d · kasa %%%.0f",
                  nData, nSide, nSideAfford, nSideDip, nUp, nUpAfford, nDown, PositionsTotal(), TotalNotional()/eq*100.0);
      if(nSideDip==0 && nUpAfford==0)
         Print("→ İşlem yok: uygun-fiyatlı + dip'teki yatay hisse yok, uygun yukarı-trend yok. (Bütçe uygun azsa → birim %% artır ya da ucuz hisse)");
   }
}
//+------------------------------------------------------------------+
