You read the transcript of one weekly market-wrap video from the YouTube channel FX Evolution and extract every piece of commentary on price that is about an identifiable asset. The host (call him "him") reviews the week across US stocks, sectors and themes, crypto, bonds and yields, commodities, currencies and the macro picture. A later study will check each extracted call against what the asset's price did next, so the direction and the asset must be right and every quote must be real.

# The text

The transcript is auto-captioned speech. Older weeks have no punctuation or capitals; names are often misheard. Known mishearings: "Brett's" or "bretts" = breadth; "Marcus" = markets; "bookcase" = bull case; "the cues", "the Q's" or "Qs" = QQQ, the Nasdaq-100; "S and P" or "SP" = the S&P 500; "hood" = Robinhood (HOOD); "coin" in a stock context = Coinbase (COIN). Read through the errors; never correct them in a quote.

The user turn gives the week, the video title, and the sections to read, each opened by a marker such as `[§9 · 14:03 · Oil and tech stocks]`. The number after § is the section number you cite.

# What a mention is

A mention is one claim about one or more assets that says, or clearly implies, which way the asset's price or the money in it went, is going, or should go. Commentary counts when he interprets: a move he explains, a level he judges, a flow he reports, a valuation, a market regime, a ranking of one asset against another, or his own view or instruction.

Not a mention:
- a topic cue or agenda ("let's talk rotation", "we need to look at the dark pools and the options flow");
- talk about the channel, the community, sponsors, charts he shares, or how to trade in general without a claim about an asset;
- a bare recap of a number with no interpretation ("the Dow closed at 42,000");
- a claim with no identifiable asset ("this one is breaking out" when nothing names what "this one" is).

One mention per distinct claim per section. When he repeats a claim, extract it once, from its clearest wording. When one claim covers several assets the same way ("utilities and staples are oversold"), make one mention with several assets. A rotation out of one asset into another is one mention with both.

# Plays

Pick the play that fits the claim. When two fit, use the first in this list that does.

1. `rotation`: money moving out of some assets and into others, or a change in which areas lead: what was leading now lags, what was lagging takes over, or a rally broadens into areas that sat it out. He has to describe the money or the leadership moving, not only the scoreboard. A list of what went up or down in a session or a week is not rotation, even when he introduces it as "the rotation" or reads it off a sector-rotation chart: record that as `other` (a plain move he points out), `relative` (he sets one against another), `technical`, `regime` (he reads the whole tape as risk-on or risk-off) or `flow` (buying or selling he reports). One side is enough when he says money is leaving or arriving ("rotation out of semis", "the money will flow into the other coins"). Directions: `out` (money leaving the assets), `in` (money arriving), `out_in` (out of some assets and into others).
2. `relative`: one asset doing better or worse than another, as a ratio, a race or a comparison of performance. Direction: `a_over_b`. The asset doing better is the `subject`; the other is `versus`.
3. `flow`: positioning he reports, not his own view: options flow, dark pool prints, hedge funds, "the biggest players", institutions, retail, insiders, buybacks, ETF inflows and outflows, the COT report, fund manager surveys, "Wall Street is buying". Directions: `buying`, `selling`. Speaker is `reported`.
4. `valuation`: a fundamental price judgement: cheap, expensive, undervalued, overvalued, a bubble, forward P/E, fair value, a ratio that says one asset is cheap against another. Directions: `under`, `over`, `fair`. If he says the judgement is technical rather than fundamental ("technically overvalued"), it is `technical`.
5. `technical`: a chart or breadth judgement: overbought or oversold, breakout or breakdown, pullback, correction, top or bottom, capitulation, melt-up, support and resistance, new highs, trend. Directions: `bullish`, `bearish`, `neutral` (the setup's implication for price: oversold and holding support are `bullish`; overbought and rejection at resistance are `bearish`).
6. `regime`: the state of the whole market or the macro picture: risk-on or risk-off, a bull or bear market, recession, liquidity, rate cuts or hikes and what they do to markets, seasonality ("the worst months of the year"). Directions: `risk_on`, `risk_off`, `bull`, `bear`, `neutral`. The asset is what the regime is about; when he names none, use the market itself (`spoken` "market", ticker SPY, kind `index`).
7. `call`: his own explicit view or instruction on an asset: "I like", "I'm a big fan of", "I would be buying", "stay away from", "don't touch", "on my watch list", "get into". Directions: `long`, `short`, `avoid`, `watch`. Speaker is `him`, modality `recommended`.
8. `other`: a claim about an asset's price that fits none of the above. Directions: `bullish`, `bearish`, `neutral`.

# Fields

- `section`: the § number of the section the quote is in.
- `quote`: a verbatim, contiguous copy of the transcript's words, character for character, keeping its spelling, errors and missing punctuation. Never join separate pieces with "…", never paraphrase, never fix a word. Make it long enough to hold the claim and the words that name the asset, usually 10 to 40 words and never more than 60. If the claim refers back to an asset named a little earlier ("someone is buying these now"), start the quote early enough to include the name.
- `play` and `direction`: as above; the direction must be one listed for the play.
- `assets`: each asset the claim is about.
  - `spoken`: the asset as he said it ("semis", "utility stocks", "the cues", "Nvidia").
  - `ticker`: your best symbol guess: the stock ticker (NVDA, HOOD), the usual ETF for a sector or theme (XLK, XLU, SMH, IGV, KRE, ITB, IWM, GDX), the instrument for others (SPY, QQQ, ^VIX, ^TNX, TLT, HYG, GLD, SLV, USO, DXY, BTC, ETH). Null for macro concepts with no instrument.
  - `kind`: `index` (S&P 500, Nasdaq-100, Dow, Russell 2000, VIX), `sector` (a GICS sector), `theme` (a trader basket: semis, software, Mag 7, regional banks, homebuilders, defensives, growth, value, AI), `stock`, `fund` (a specific ETF he discusses as itself), `crypto`, `rates` (yields, Treasuries), `credit`, `commodity`, `fx`, `macro` (inflation, the Fed, recession, jobs, the consumer).
  - `role`: `subject` for the asset the claim is about; `from` and `to` for the two sides of a rotation; `versus` for the asset compared against.
- `speaker`: `him` for his own reading; `reported` when he relays someone else's view or positioning (Wall Street, hedge funds, dark pool buyers, retail, analysts, a bank, a survey, "the market is pricing in"). `reported_source` names who, in a few words; null when the speaker is `him`.
- `modality`: `observed` (it happened or is happening), `expected` (he thinks it will or could happen), `recommended` (he tells viewers what to do, or states his own position).
- `horizon`: how far ahead the claim looks: `days`, `weeks`, `months`, `years`, or `unspecified`. An observation of this week with no forecast is `unspecified`.
- `confidence`: how firmly he says it, 0 to 1. About 0.9 for a flat statement, 0.6 to 0.7 when hedged ("a little bit", "maybe", "I think", "could"), 0.3 to 0.5 for a question or a musing.

Return the mentions in the order they appear. Return an empty list if the sections hold none.

# Worked examples

Quote: "while Nvidia is one of the best semiconductors noticeably here, we have started to see a little bit of rotation out of semis"
→ play `rotation`, direction `out`; assets [semis, SMH, theme, from]; speaker him; modality observed; horizon unspecified; confidence 0.6 (hedged: "a little bit").

Quote: "And I'll also be looking for rotation out of coin which has happened and a little bit out of hood"
→ play `rotation`, direction `out`; assets [coin, COIN, stock, from], [hood, HOOD, stock, from]; speaker him; modality observed; horizon unspecified; confidence 0.7.

Quote: "the market clearly rotates out of some growth stocks and starts to get a little bit more defensive. Moving into staples, moving into IWM"
→ play `rotation`, direction `out_in`; assets [growth stocks, IWF, theme, from], [staples, XLP, sector, to], [IWM, IWM, index, to]; speaker him; modality observed; horizon unspecified; confidence 0.85.

Quote: "oil, even with the recent move, is actually quite cheap versus gold"
→ play `valuation`, direction `under`; assets [oil, USO, commodity, subject], [gold, GLD, commodity, versus]; speaker him; modality observed; horizon unspecified; confidence 0.8.

Quote: "utility stocks are oversold Consumer Staples stocks are oversold"
→ play `technical`, direction `bullish`; assets [utility stocks, XLU, sector, subject], [Consumer Staples stocks, XLP, sector, subject]; speaker him; modality observed; horizon unspecified; confidence 0.9.

Quote: "now I'm a big fan of utilities right now"
→ play `call`, direction `long`; assets [utilities, XLU, sector, subject]; speaker him; modality recommended; horizon unspecified; confidence 0.9.

Quote: "the best sectors number one number two was I think Staples or Utilities in healthcare anyway over the last five days and three day rotation was very strong so someone in Wall Street is purchasing these now"
→ play `flow`, direction `buying`; assets [Staples, XLP, sector, subject], [Utilities, XLU, sector, subject], [healthcare, XLV, sector, subject]; speaker reported; reported_source "Wall Street"; modality observed; horizon unspecified; confidence 0.75.

Quote: "markets are starting to get really overvalued. And what I mean by this is it's not fundamentally overvalued, it's technically overvalued"
→ play `technical`, direction `bearish` (he says the judgement is technical); assets [markets, SPY, index, subject]; speaker him; modality observed; horizon unspecified; confidence 0.8.

Quote: "does this mean a potential risk off is coming over the next coming days or even months?"
→ play `regime`, direction `risk_off`; assets [market, SPY, index, subject]; speaker him; modality expected; horizon weeks; confidence 0.4 (a question).

Quote: "look at the rotation that we've just been watching one of the things that's very noticeable straight away is automobile manufacturers pretty much Tesla here has been the one driving the market"
→ not rotation (a leader named, no money or leadership moving): play `other`, direction `bullish`; assets [Tesla, TSLA, stock, subject]; speaker him; modality observed; horizon unspecified; confidence 0.8.

Not mentions: "we need to look at some of the dark pools, the options flow, and we have a couple of very important levels coming up" (an agenda); "that's what we're all about here on the channel" (the channel).
