(() => {
  "use strict";

  const MARKETS={sp500:"S&P 500",nq:"Nasdaq-100",vix:"VIX Futures",rty:"Russell 2000",dow:"Dow Jones",gold:"Gold",silver:"Silver"};
  const MARKET_ORDER=Object.keys(MARKETS);
  const ROLE_ORDER={PRIMARY_DIRECTIONAL:0,SECONDARY_DIRECTIONAL:1,INTERMEDIARY_CONTEXT:2,HEDGER_CONTEXT:2,OPPOSITE_SIDE_CONTEXT:2,AGGREGATE_CONTEXT:2};
  const ROLE_LABEL={PRIMARY_DIRECTIONAL:"Primary",SECONDARY_DIRECTIONAL:"Secondary",INTERMEDIARY_CONTEXT:"Intermediary",HEDGER_CONTEXT:"Hedger",OPPOSITE_SIDE_CONTEXT:"Opposite-side",AGGREGATE_CONTEXT:"Aggregate"};
  const EVIDENCE_ORDER={PROSPECTIVE_CONFIRMED:8,GLOBAL_FDR:7,FAMILY_FDR:6,NONOVERLAP_CONFIRMED:5,HOLDOUT_DIRECTION_CONFIRMED:4,OOS_PLUS_OVERLAP:3,OOS_ONLY:3,DISCOVERY_ONLY:2,DESCRIPTIVE_ONLY:1,INSUFFICIENT_N:0};
  const EVIDENCE_LABEL={PROSPECTIVE_CONFIRMED:"Live confirmed",GLOBAL_FDR:"Global FDR",FAMILY_FDR:"Family FDR",NONOVERLAP_CONFIRMED:"Non-overlap confirmed",HOLDOUT_DIRECTION_CONFIRMED:"Holdout direction",OOS_PLUS_OVERLAP:"OOS + overlap",OOS_ONLY:"OOS only",DISCOVERY_ONLY:"Discovery only",DESCRIPTIVE_ONLY:"Descriptive",INSUFFICIENT_N:"Insufficient independent N"};
  const FORWARD=["1w","2w","4w","13w","26w"];
  const WATCH_CLASSES=new Set(["GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED"]);
  const state={current:null,active:null,live:null,registry:null,sentiment:null,market:"sp500",horizon:"1w"};

  const finite=v=>{if(v===null||v===undefined||v==="")return null;const n=Number(v);return Number.isFinite(n)?n:null};
  const sign=v=>{const n=finite(v);return n===null||Math.abs(n)<.05?0:n>0?1:-1};

  async function fetchJson(path,optional=false){
    try{
      const version=window.__COT_RUNTIME_VERSION__||Date.now();
      const r=await fetch(`${path}?v=${encodeURIComponent(version)}-${Date.now()}`,{cache:"no-store"});
      if(!r.ok)throw new Error(`${path} HTTP ${r.status}`);
      return await r.json();
    }catch(error){
      if(!optional)throw error;
      console.warn(`Current Edge optional source unavailable: ${path}`,error);
      return null;
    }
  }

  function currentRows(market=state.market){
    return Object.values(state.current?.actor_states||{}).filter(r=>r?.market===market).sort((a,b)=>(ROLE_ORDER[a.actor_role]??9)-(ROLE_ORDER[b.actor_role]??9)||String(a.actor_label||"").localeCompare(String(b.actor_label||"")));
  }
  function activeRows(market=state.market){return state.active?.by_market?.[market]?.active_thresholds||[]}
  function metricFor(row,horizon){return (row?.metrics||[]).find(m=>m?.horizon===horizon)||null}
  function evidenceStatus(row,metric){return String(metric?.evidence_status||row?.evidence_status||row?.historical_classification||"DISCOVERY_ONLY")}
  function evidenceGrade(status){const s=String(status||"");if(s==="PROSPECTIVE_CONFIRMED"||s==="GLOBAL_FDR"||s==="FAMILY_FDR")return{grade:"A",label:EVIDENCE_LABEL[s]||s,tone:"strong"};if(s==="NONOVERLAP_CONFIRMED"||s==="HOLDOUT_DIRECTION_CONFIRMED")return{grade:"B",label:EVIDENCE_LABEL[s]||s,tone:"supported"};if(s==="DISCOVERY_ONLY"||s==="OOS_ONLY"||s==="OOS_PLUS_OVERLAP")return{grade:"C",label:EVIDENCE_LABEL[s]||s,tone:"mixed"};return{grade:"D",label:EVIDENCE_LABEL[s]||s,tone:"weak"}}
  function sampleLabel(n){const v=finite(n);if(v===null)return"N unavailable";if(v>=60)return"Full sample";if(v>=30)return"Sample warning";if(v>=15)return"Research-only N";return"Insufficient N"}

  function rankedEdges(horizon=state.horizon,market=state.market){
    return activeRows(market).map(row=>({row,metric:metricFor(row,horizon)})).filter(x=>x.metric&&finite(x.metric.excess_vs_baseline_pp)!==null).sort((a,b)=>(EVIDENCE_ORDER[evidenceStatus(b.row,b.metric)]??0)-(EVIDENCE_ORDER[evidenceStatus(a.row,a.metric)]??0)||Math.abs(finite(b.metric.excess_vs_baseline_pp)||0)-Math.abs(finite(a.metric.excess_vs_baseline_pp)||0)||(ROLE_ORDER[a.row.actor_role]??9)-(ROLE_ORDER[b.row.actor_role]??9)||(finite(b.metric.independent_n)||finite(b.metric.n)||0)-(finite(a.metric.independent_n)||finite(a.metric.n)||0));
  }
  function edgeDirection(metric){const edge=finite(metric?.excess_vs_baseline_pp);if(edge===null||Math.abs(edge)<.05)return{label:"NEUTRAL",tone:"neutral",sign:0};return edge>0?{label:"BULLISH",tone:"positive",sign:1}:{label:"BEARISH",tone:"negative",sign:-1}}
  function modelTone(signal){const text=String(signal||"").toLowerCase();if(/bull|long|risk.?on|construct|support/.test(text))return"positive";if(/bear|short|risk.?off|defens|restrict/.test(text))return"negative";return"neutral"}
  function toneSign(tone){return tone==="positive"?1:tone==="negative"?-1:0}

  function corePrediction(market=state.market){const rows=(state.live?.current_predictions||[]).filter(r=>r?.market===market),combined=rows.filter(r=>r?.model_family==="combined");return(combined.length?combined:rows).at(-1)||null}
  function actorLivePredictions(market=state.market){return(state.live?.edge_evidence?.current_predictions||[]).filter(r=>r?.market===market)}
  function reportDates(market=state.market){const rows=currentRows(market),report=[...new Set(rows.map(r=>r.report_date_tuesday).filter(Boolean))].sort().at(-1)||null,release=[...new Set(rows.map(r=>r.release_date_friday).filter(Boolean))].sort().at(-1)||null;return{report,release}}
  function edgeExplanation(item){if(!item)return"";const m=item.metric,status=evidenceStatus(item.row,m),edge=finite(m?.excess_vs_baseline_pp),n=finite(m?.independent_n??m?.n),base=finite(m?.baseline_return_pct),conditional=finite(m?.conditional_return_pct);const pieces=[`${EVIDENCE_LABEL[status]||status}`];if(edge!==null)pieces.push(`historical excess ${edge>=0?"+":""}${edge.toFixed(2)} pp vs baseline`);if(conditional!==null&&base!==null)pieces.push(`conditional ${conditional.toFixed(2)}% vs baseline ${base.toFixed(2)}%`);if(n!==null)pieces.push(`independent N ${Math.trunc(n)}`);return pieces.join(" · ")}

  function directionalRead(market=state.market,horizon=state.horizon){
    const ranked=rankedEdges(horizon,market),model=corePrediction(market),strongest=ranked[0]||null;
    if(model?.signal){return{label:String(model.signal).toUpperCase(),tone:modelTone(model.signal),source:"prospective",strongest,opposition:null,ranked,model,detail:"Prospective combined model is frozen separately from historical actor edges."}}
    if(!strongest)return{label:"NO ACTIVE EDGE",tone:"neutral",source:"historical",strongest:null,opposition:null,ranked,model:null,detail:"No release-corrected percentile threshold is active at the selected horizon."};
    const dir=edgeDirection(strongest.metric),strength=Math.abs(finite(strongest.metric.excess_vs_baseline_pp)||0);
    const opposition=ranked.find(item=>edgeDirection(item.metric).sign===-dir.sign)||null;
    const opposingStrength=Math.abs(finite(opposition?.metric?.excess_vs_baseline_pp)||0);
    const sameEvidence=opposition&&(EVIDENCE_ORDER[evidenceStatus(opposition.row,opposition.metric)]??0)>=(EVIDENCE_ORDER[evidenceStatus(strongest.row,strongest.metric)]??0)-1;
    const conflicted=Boolean(opposition&&sameEvidence&&opposingStrength>=strength*.75);
    const label=conflicted?"MIXED ACTIVE EDGES":`${dir.label} HISTORICAL EDGE`;
    return{label,tone:conflicted?"neutral":dir.tone,source:"historical",strongest,opposition,ranked,model:null,detail:`Headline is a display synthesis of frozen release-corrected evidence. ${edgeExplanation(strongest)}. Actor edges are ranked, never summed.`};
  }
  function summary(){const read=directionalRead();const bullish=read.ranked.filter(x=>edgeDirection(x.metric).sign>0).length,bearish=read.ranked.filter(x=>edgeDirection(x.metric).sign<0).length;return{...read,bullish,bearish}}

  function bestForwardMetric(row){
    const metrics=FORWARD.map(h=>metricFor(row,h)).filter(m=>finite(m?.excess_vs_baseline_pp)!==null);
    return metrics.sort((a,b)=>(EVIDENCE_ORDER[evidenceStatus(row,b)]??0)-(EVIDENCE_ORDER[evidenceStatus(row,a)]??0)||Math.abs(finite(b.excess_vs_baseline_pp)||0)-Math.abs(finite(a.excess_vs_baseline_pp)||0))[0]||null;
  }
  function marketOpportunities(){
    return MARKET_ORDER.map(market=>{
      const rows=activeRows(market),items=rows.map(row=>({row,metric:bestForwardMetric(row)})).filter(x=>x.metric);
      items.sort((a,b)=>(EVIDENCE_ORDER[evidenceStatus(b.row,b.metric)]??0)-(EVIDENCE_ORDER[evidenceStatus(a.row,a.metric)]??0)||Math.abs(finite(b.metric.excess_vs_baseline_pp)||0)-Math.abs(finite(a.metric.excess_vs_baseline_pp)||0));
      const top=items[0]||null,dir=edgeDirection(top?.metric),opposite=items.filter(x=>edgeDirection(x.metric).sign===-dir.sign).length;
      return{market,label:MARKETS[market],activeCount:rows.length,top,direction:dir,opposingCount:opposite,reportDates:reportDates(market)};
    }).sort((a,b)=>Boolean(b.top)-Boolean(a.top)||((EVIDENCE_ORDER[evidenceStatus(b.top?.row,b.top?.metric)]??0)-(EVIDENCE_ORDER[evidenceStatus(a.top?.row,a.top?.metric)]??0))||Math.abs(finite(b.top?.metric?.excess_vs_baseline_pp)||0)-Math.abs(finite(a.top?.metric?.excess_vs_baseline_pp)||0));
  }

  function thresholdWatchlist(limit=8){
    const edges=Object.values(state.registry?.threshold_edges||{}),rows=Object.values(state.current?.actor_states||{}),candidates=[];
    for(const row of rows){
      const magnitude=finite(row.change_magnitude_percentile),direction=String(row.direction||"");
      if(magnitude===null||!['ADD','CUT'].includes(direction))continue;
      const future=edges.filter(edge=>edge.series===row.series&&edge.direction===direction&&WATCH_CLASSES.has(String(edge.best_classification||""))&&finite(edge.threshold)!==null&&finite(edge.threshold)>magnitude).map(edge=>({...edge,distance:finite(edge.threshold)-magnitude})).sort((a,b)=>a.distance-b.distance||(EVIDENCE_ORDER[b.best_classification]??0)-(EVIDENCE_ORDER[a.best_classification]??0));
      if(!future.length)continue;
      const edge=future[0],edgeSign=sign(edge.best_holdout_edge_pp),edgeDirection=edgeSign>0?{label:"BULLISH",tone:"positive"}:edgeSign<0?{label:"BEARISH",tone:"negative"}:{label:"NEUTRAL",tone:"neutral"};
      candidates.push({market:row.market,row,edge,distance:edge.distance,direction:edgeDirection,grade:evidenceGrade(edge.best_classification)});
    }
    return candidates.sort((a,b)=>a.distance-b.distance||(EVIDENCE_ORDER[b.edge.best_classification]??0)-(EVIDENCE_ORDER[a.edge.best_classification]??0)||Math.abs(finite(b.edge.best_holdout_edge_pp)||0)-Math.abs(finite(a.edge.best_holdout_edge_pp)||0)).slice(0,limit);
  }

  function findMetric(root,keys,depth=0,seen=new Set()){
    if(!root||depth>9||typeof root!=="object"||seen.has(root))return null;
    seen.add(root);
    if(Array.isArray(root)){for(let i=root.length-1;i>=0;i--){const found=findMetric(root[i],keys,depth+1,seen);if(found!==null)return found}return null}
    for(const key of keys){if(Object.prototype.hasOwnProperty.call(root,key)){const value=finite(root[key]);if(value!==null)return value}}
    for(const key of ["latest","current","state"]){const found=findMetric(root[key],keys,depth+1,seen);if(found!==null)return found}
    for(const [key,value] of Object.entries(root)){if(["latest","current","state"].includes(key))continue;const found=findMetric(value,keys,depth+1,seen);if(found!==null)return found}
    return null;
  }
  function macroSnapshot(){
    const root=window.__COT_WORLDCLASS_BASE__?.MACRO_MONITOR||null;
    const score=findMetric(root,["liquidity_score","macro_score","unified_score","score"]);
    const tone=score===null?"neutral":score>=60?"positive":score<=40?"negative":"neutral";
    const label=score===null?"UNAVAILABLE":score>=70?"STRONGLY SUPPORTIVE":score>=60?"SUPPORTIVE":score<=30?"STRONGLY RESTRICTIVE":score<=40?"RESTRICTIVE":"NEUTRAL";
    return{score,tone,label,available:score!==null,drivers:[
      {key:"liquidity",label:"Net liquidity · 4W",value:findMetric(root,["net_liquidity_4w_change"]) ,suffix:" bn"},
      {key:"reserves",label:"Bank reserves · 4W",value:findMetric(root,["bank_reserves_4w_change"]) ,suffix:" bn"},
      {key:"funding",label:"SOFR − IORB",value:findMetric(root,["sofr_iorb_spread"]),suffix:" pp"},
      {key:"real_yield",label:"10Y real yield",value:findMetric(root,["real_yield_10y","dfii10"]),suffix:"%"},
      {key:"credit",label:"HY OAS",value:findMetric(root,["hy_oas"]),suffix:"%"}
    ]};
  }
  function factorSentiment(){
    const stats=window.__COT_WORLDCLASS_BASE__?.FACTOR_DATA?.stats?.[state.market]||{},row=stats.cnn_fear_greed||Object.values(stats).find(item=>String(item?.key||"")==="cnn_fear_greed"||/fear.*greed/i.test(String(item?.label||"")))||null,index=finite(row?.latest_value);
    if(index===null)return null;
    const label=index>=75?"EXTREME GREED":index>=55?"GREED":index<=25?"EXTREME FEAR":index<=45?"FEAR":"NEUTRAL";
    return{available:true,tone:index>=60?"positive":index<=40?"negative":"neutral",label,index,detail:`CNN Fear & Greed · percentile ${finite(row?.percentile)===null?"n/a":`P${Math.round(finite(row.percentile))}`}`,sources:1,date:row?.latest_date||null,source:"CNN Fear & Greed"};
  }
  function sentimentSnapshot(){
    const latest=state.sentiment?.latest||null,composite=latest?.composite||null,index=finite(composite?.sentiment_index);
    if(latest&&index!==null){const tone=index>=60?"positive":index<=40?"negative":"neutral",crowding=index>=75?"CROWDED BULLISH":index<=25?"CROWDED BEARISH":String(composite.regime||composite.state||"BALANCED").toUpperCase();return{available:true,tone,label:crowding,index,detail:`Authenticated composite · ${composite.available_sources??0}/${composite.required_sources??4} sources · bullish ${finite(composite.bullish_pct)?.toFixed(0)??"n/a"}% · bearish ${finite(composite.bearish_pct)?.toFixed(0)??"n/a"}%`,sources:composite.available_sources??0,date:latest.observation_date,source:"authenticated composite"}}
    return factorSentiment()||{available:false,tone:"neutral",label:"UNAVAILABLE",index:null,detail:"No authenticated sentiment or governed Fear & Greed observation; no neutral value is fabricated.",sources:0,source:"none"};
  }
  function layerAlignment(market=state.market){
    const read=directionalRead(market,state.horizon),macro=macroSnapshot(),sentiment=sentimentSnapshot();
    const layers=[{available:Boolean(read.strongest||read.model),sign:toneSign(read.tone)},{available:macro.available,sign:toneSign(macro.tone)},{available:sentiment.available,sign:toneSign(sentiment.tone)}],available=layers.filter(x=>x.available),directional=available.map(x=>x.sign).filter(Boolean);
    let label=available.length<2?"INSUFFICIENT LAYERS":"CONFLICTED",tone="neutral",count=0;
    if(directional.length>=2){const pos=directional.filter(x=>x>0).length,neg=directional.filter(x=>x<0).length;count=Math.max(pos,neg);if(count===directional.length){label=`${count} / ${available.length} ALIGNMENT`;tone=pos===count?"positive":"negative"}else if(count>=2){label=`${count} / ${available.length} ALIGNMENT`;tone=pos===count?"positive":"negative"}}
    else if(available.length>=2)label="MIXED / NEUTRAL";
    return{label,tone,count,read,macro,sentiment,availableCount:available.length,note:"Alignment is descriptive context only; COT, macro and sentiment are not summed into a synthetic trading score."};
  }

  function selectedMarket(){const m=document.querySelector("#instrumentTabs [data-market].active")?.dataset.market;return MARKETS[m]?m:state.market}
  async function load(){
    const[current,active,live,registry,sentiment]=await Promise.all([
      fetchJson("worldclass/cot-current-state.json"),fetchJson("worldclass/cot-active-edges.json"),fetchJson("worldclass/live-track-record.json",true),fetchJson("worldclass/cot-edge-registry.json"),fetchJson("worldclass/market-sentiment.json",true)
    ]);
    state.current=current;state.active=active;state.live=live||{};state.registry=registry;state.sentiment=sentiment||{};state.market=selectedMarket();return state;
  }

  function edgeGrade(metric){return metric?evidenceGrade(evidenceStatus(null,metric)):null}
  function liveForecast(market=state.market,horizon="1w"){
    const rows=(state.live?.current_predictions||[]).filter(row=>row?.market===market),combined=rows.filter(row=>row?.model_family==="combined");
    const model=(combined.length?combined:rows).at(-1)||null;
    if(!model)return null;
    const expected=finite(model[`expected_${horizon}_return_pct`]??model[`expected_${horizon}_return`]??model?.historical_horizons?.[horizon]?.expected_return_pct);
    const probability=finite(model[`probability_positive_${horizon}`]??model[`probability_positive_${horizon}_pct`]??model?.historical_horizons?.[horizon]?.probability_positive);
    if(expected===null&&probability===null)return null;
    return{model,expected,probability,confidence:model.confidence||model?.historical_horizons?.[horizon]?.confidence||"n/a"};
  }

  window.__COT_CURRENT_EDGE_MODEL__={MARKETS,MARKET_ORDER,ROLE_ORDER,ROLE_LABEL,EVIDENCE_ORDER,EVIDENCE_LABEL,FORWARD,state,finite,currentRows,activeRows,metricFor,evidenceStatus,evidenceGrade,edgeGrade,liveForecast,sampleLabel,rankedEdges,edgeDirection,edgeExplanation,modelTone,corePrediction,actorLivePredictions,reportDates,directionalRead,summary,bestForwardMetric,marketOpportunities,thresholdWatchlist,macroSnapshot,factorSentiment,sentimentSnapshot,layerAlignment,selectedMarket,load};
})();
