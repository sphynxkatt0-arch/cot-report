(() => {
  "use strict";

  const MARKETS={sp500:"S&P 500",nq:"Nasdaq-100",vix:"VIX Futures",rty:"Russell 2000",dow:"Dow Jones",gold:"Gold",silver:"Silver"};
  const MARKET_ORDER=Object.keys(MARKETS);
  const ROLE_ORDER={PRIMARY_DIRECTIONAL:0,SECONDARY_DIRECTIONAL:1,INTERMEDIARY_CONTEXT:2,HEDGER_CONTEXT:2,OPPOSITE_SIDE_CONTEXT:2,AGGREGATE_CONTEXT:2};
  const ROLE_LABEL={PRIMARY_DIRECTIONAL:"Primary",SECONDARY_DIRECTIONAL:"Secondary",INTERMEDIARY_CONTEXT:"Intermediary",HEDGER_CONTEXT:"Hedger",OPPOSITE_SIDE_CONTEXT:"Opposite-side",AGGREGATE_CONTEXT:"Aggregate"};
  const PRIMARY_DATASET={sp500:"tff",nq:"tff",vix:"tff",rty:"tff",dow:"tff",gold:"disaggregated",silver:"disaggregated"};
  const NONREPORTABLE_ACTORS=new Set(["non_reportable","nonreportable"]);
  const EVIDENCE_ORDER={PROSPECTIVE_CONFIRMED:8,GLOBAL_FDR:7,FAMILY_FDR:6,NONOVERLAP_CONFIRMED:5,HOLDOUT_DIRECTION_CONFIRMED:4,OOS_PLUS_OVERLAP:3,OOS_ONLY:3,DISCOVERY_ONLY:2,DESCRIPTIVE_ONLY:1,INSUFFICIENT_N:0};
  const EVIDENCE_LABEL={PROSPECTIVE_CONFIRMED:"Live confirmed",GLOBAL_FDR:"Global FDR",FAMILY_FDR:"Family FDR",NONOVERLAP_CONFIRMED:"Non-overlap confirmed",HOLDOUT_DIRECTION_CONFIRMED:"Holdout direction",OOS_PLUS_OVERLAP:"OOS + overlap",OOS_ONLY:"OOS only",DISCOVERY_ONLY:"Discovery only",DESCRIPTIVE_ONLY:"Descriptive",INSUFFICIENT_N:"Insufficient independent N"};
  const FORWARD=["1w","2w","4w","13w","26w"];
  const WATCH_CLASSES=new Set(["GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED"]);
  const VALIDATED_CLASSES=new Set(["GLOBAL_FDR","FAMILY_FDR","NONOVERLAP_CONFIRMED","HOLDOUT_DIRECTION_CONFIRMED"]);
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
  function allActorStates(){return{...(state.current?.all_taxonomy_actor_states||{}),...(state.current?.actor_states||{})}}
  function actorState(series){return state.current?.actor_states?.[series]||state.current?.all_taxonomy_actor_states?.[series]||null}
  function actorKey(row){return String(row?.series||"").split(":").at(-1)||""}
  function isCanonicalActiveRow(row,market){
    if(String(row?.actor_role||"")==="AGGREGATE_CONTEXT")return false;
    const primary=PRIMARY_DATASET[market],actor=actorKey(row);
    if(primary&&NONREPORTABLE_ACTORS.has(actor)&&String(row?.dataset||"")!==primary)return false;
    return true;
  }
  function selectionFor(row,horizon=state.horizon){
    const selection=row?.horizon_selections?.[horizon];
    if(selection?.selected_threshold!==undefined&&selection?.selected_threshold!==null)return selection;
    return{selected_threshold:row?.selected_threshold,evidence_status:row?.evidence_status||row?.historical_classification,independent_n:metricForLegacy(row,horizon)?.independent_n,excess_vs_baseline_pp:metricForLegacy(row,horizon)?.excess_vs_baseline_pp};
  }
  function metricForLegacy(row,horizon){return (row?.metrics||[]).find(m=>m?.horizon===horizon)||null}
  function profileFor(row,selectedHorizon=state.horizon){
    const selection=selectionFor(row,selectedHorizon),threshold=selection?.selected_threshold;
    return row?.threshold_profiles?.[String(threshold)]||row?.metrics||[];
  }
  function effectiveRow(row,selectedHorizon=state.horizon){
    const selection=selectionFor(row,selectedHorizon),metrics=profileFor(row,selectedHorizon);
    return{...row,selected_threshold:selection?.selected_threshold??row?.selected_threshold,evidence_status:selection?.evidence_status||row?.evidence_status,historical_classification:selection?.evidence_status||row?.historical_classification,metrics,_selected_horizon:selectedHorizon};
  }
  function activeRows(market=state.market,horizon=state.horizon){
    const rows=(state.active?.all_taxonomy_by_market||state.active?.by_market||{})?.[market]?.active_thresholds||[];
    return rows.filter(row=>isCanonicalActiveRow(row,market)).filter(row=>{
      const current=actorState(row.series);
      if(!current)return false;
      const threshold=finite(selectionFor(row,horizon)?.selected_threshold);
      const magnitude=finite(current.change_magnitude_percentile);
      return current.direction===row.direction&&threshold!==null&&magnitude!==null&&magnitude>=threshold;
    });
  }
  function metricFor(row,horizon,selectedHorizon=row?._selected_horizon||horizon){return profileFor(row,selectedHorizon).find(m=>m?.horizon===horizon)||null}
  function evidenceStatus(row,metric){return String(metric?.evidence_status||row?.evidence_status||row?.historical_classification||"DISCOVERY_ONLY")}
  function evidenceGrade(status){const s=String(status||"");if(s==="PROSPECTIVE_CONFIRMED"||s==="GLOBAL_FDR"||s==="FAMILY_FDR")return{grade:"A",label:EVIDENCE_LABEL[s]||s,tone:"strong"};if(s==="NONOVERLAP_CONFIRMED"||s==="HOLDOUT_DIRECTION_CONFIRMED")return{grade:"B",label:EVIDENCE_LABEL[s]||s,tone:"supported"};if(s==="DISCOVERY_ONLY"||s==="OOS_ONLY"||s==="OOS_PLUS_OVERLAP")return{grade:"C",label:EVIDENCE_LABEL[s]||s,tone:"mixed"};return{grade:"D",label:EVIDENCE_LABEL[s]||s,tone:"weak"}}
  function sampleLabel(n){const v=finite(n);if(v===null)return"N unavailable";if(v>=60)return"Full sample";if(v>=30)return"Sample warning";if(v>=15)return"Research-only N";return"Insufficient N"}

  function rankedEdges(horizon=state.horizon,market=state.market,{validatedOnly=false}={}){
    return activeRows(market,horizon).map(sourceRow=>{const current=actorState(sourceRow.series),row={...effectiveRow(sourceRow,horizon),current_change_percentile:current?.change_magnitude_percentile,change_magnitude_percentile:current?.change_magnitude_percentile};return{row,sourceRow,metric:metricFor(row,horizon,horizon)}}).filter(x=>x.metric&&finite(x.metric.excess_vs_baseline_pp)!==null&&(!validatedOnly||(VALIDATED_CLASSES.has(evidenceStatus(x.row,x.metric))&&finite(x.metric.independent_n)>=15))).sort((a,b)=>(EVIDENCE_ORDER[evidenceStatus(b.row,b.metric)]??0)-(EVIDENCE_ORDER[evidenceStatus(a.row,a.metric)]??0)||Math.abs(finite(b.metric.excess_vs_baseline_pp)||0)-Math.abs(finite(a.metric.excess_vs_baseline_pp)||0)||(finite(b.metric.independent_n)||finite(b.metric.n)||0)-(finite(a.metric.independent_n)||finite(a.metric.n)||0)||(ROLE_ORDER[a.row.actor_role]??9)-(ROLE_ORDER[b.row.actor_role]??9));
  }
  function edgeDirection(metric){const edge=finite(metric?.excess_vs_baseline_pp);if(edge===null||Math.abs(edge)<.05)return{label:"NEUTRAL",tone:"neutral",sign:0};return edge>0?{label:"BULLISH",tone:"positive",sign:1}:{label:"BEARISH",tone:"negative",sign:-1}}
  function modelTone(signal){const text=String(signal||"").toLowerCase();if(/bull|long|risk.?on|construct|support/.test(text))return"positive";if(/bear|short|risk.?off|defens|restrict/.test(text))return"negative";return"neutral"}
  function toneSign(tone){return tone==="positive"?1:tone==="negative"?-1:0}

  function matchingLivePredictions(market=state.market,family="combined"){
    const report=reportDates(market).report;
    // Older presentation files omitted these identities; recover them only
    // from the matching immutable signal audit, never from today's header.
    const audits=new Map((state.live?.history||[]).map(row=>[row.signal_id,row]));
    return(state.live?.current_predictions||[]).map(row=>({...audits.get(row.signal_id),...row})).filter(row=>
      row.market===market&&row.model_family===family&&row.report_date===report&&row.created_at_utc&&row.forecast_hash
    ).sort((a,b)=>String(a.created_at_utc).localeCompare(String(b.created_at_utc)));
  }
  function corePrediction(market=state.market){return matchingLivePredictions(market).at(-1)||null}
  function actorLivePredictions(market=state.market){return(state.live?.edge_evidence?.current_predictions||[]).filter(r=>r?.market===market)}
  function reportDates(market=state.market){const rows=currentRows(market),report=[...new Set(rows.map(r=>r.report_date_tuesday).filter(Boolean))].sort().at(-1)||null,release=[...new Set(rows.map(r=>r.release_date_friday).filter(Boolean))].sort().at(-1)||null;return{report,release}}

  const ACTOR_ROLES={tff:{asset_mgr:"PRIMARY_DIRECTIONAL",dealer:"INTERMEDIARY_CONTEXT",lev_money:"PRIMARY_DIRECTIONAL",non_reportable:"SECONDARY_DIRECTIONAL",other_reportable:"SECONDARY_DIRECTIONAL"},legacy:{commercial:"OPPOSITE_SIDE_CONTEXT",noncommercial:"PRIMARY_DIRECTIONAL",nonreportable:"SECONDARY_DIRECTIONAL",total_reportable:"AGGREGATE_CONTEXT"}};
  const percentileRank=(values,current)=>{const clean=values.map(finite).filter(v=>v!==null).sort((a,b)=>a-b);if(!clean.length||current===null)return null;let left=0,equal=0;for(const value of clean){if(value<current)left++;else if(value===current)equal++}return(left+Math.max(equal,1)/2)/clean.length*100};
  const actionType=(dl,ds,dn)=>{if(dl===null||ds===null)return dn>0?"NET_ADD":dn<0?"NET_CUT":"FLAT";if(dl>0&&ds<0)return"LONG_ADD_SHORT_COVER";if(dl<0&&ds>0)return"LONG_LIQUIDATE_SHORT_ADD";if(dl>0&&ds>=0)return dn>0?"BOTH_SIDES_ADD_LONG_DOMINANT":"BOTH_SIDES_ADD_SHORT_DOMINANT";if(dl<=0&&ds<0)return dn>0?"BOTH_SIDES_CUT_SHORT_DOMINANT":"BOTH_SIDES_CUT_LONG_DOMINANT";if(dl>0)return"LONG_ADD";if(dl<0)return"LONG_LIQUIDATE";if(ds>0)return"SHORT_ADD";if(ds<0)return"SHORT_COVER";return"FLAT"};
  function overlayRuntimeCurrent(current){
    return window.__COT_RUNTIME_COHERENCE__?.applyCurrent(current) || current;
  }
  function edgeExplanation(item){if(!item)return"";const m=item.metric,status=evidenceStatus(item.row,m),edge=finite(m?.excess_vs_baseline_pp),n=finite(m?.independent_n??m?.n),base=finite(m?.baseline_return_pct),conditional=finite(m?.conditional_return_pct);const pieces=[`${EVIDENCE_LABEL[status]||status}`];if(edge!==null)pieces.push(`historical excess ${edge>=0?"+":""}${edge.toFixed(2)} pp vs baseline`);if(conditional!==null&&base!==null)pieces.push(`conditional ${conditional.toFixed(2)}% vs baseline ${base.toFixed(2)}%`);if(n!==null)pieces.push(`independent N ${Math.trunc(n)}`);return pieces.join(" · ")}

  function directionalRead(market=state.market,horizon=state.horizon){
    const ranked=rankedEdges(horizon,market,{validatedOnly:true}),model=corePrediction(market),strongest=ranked[0]||null;
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
    const metrics=FORWARD.map(h=>{const effective=effectiveRow(row,h);return{metric:metricFor(effective,h,h),row:effective}}).filter(x=>finite(x.metric?.excess_vs_baseline_pp)!==null);
    return metrics.sort((a,b)=>(EVIDENCE_ORDER[evidenceStatus(b.row,b.metric)]??0)-(EVIDENCE_ORDER[evidenceStatus(a.row,a.metric)]??0)||Math.abs(finite(b.metric.excess_vs_baseline_pp)||0)-Math.abs(finite(a.metric.excess_vs_baseline_pp)||0))[0]?.metric||null;
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
    const edges=Object.values(state.registry?.all_taxonomy_threshold_edges||state.registry?.threshold_edges||{}),rows=Object.values(allActorStates()),candidates=[];
    for(const row of rows){
      const magnitude=finite(row.change_magnitude_percentile),direction=String(row.direction||"");
      if(magnitude===null||!['ADD','CUT'].includes(direction))continue;
      const future=edges.filter(edge=>edge.series===row.series&&edge.direction===direction&&String(edge.best_horizon||"")===state.horizon&&WATCH_CLASSES.has(String(edge.best_classification||""))&&finite(edge.best_independent_n)>=15&&finite(edge.threshold)!==null&&finite(edge.threshold)>magnitude).map(edge=>({...edge,distance:finite(edge.threshold)-magnitude})).sort((a,b)=>a.distance-b.distance||(EVIDENCE_ORDER[b.best_classification]??0)-(EVIDENCE_ORDER[a.best_classification]??0));
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
  async function waitForRuntimeCot(timeoutMs=8000){
    const started=Date.now();
    while(Date.now()-started<timeoutMs){
      if(window.__COT_WORLDCLASS_BASE__?.COT_DATA&&window.__COT_LIVE_API__?.markets)return true;
      if(window.__COT_BOOTSTRAP_ERROR__)return false;
      await new Promise(resolve=>window.setTimeout(resolve,50));
    }
    return Boolean(window.__COT_WORLDCLASS_BASE__?.COT_DATA&&window.__COT_LIVE_API__?.markets);
  }
  async function load(){
    // bootstrap.js is injected asynchronously after the release-status probe,
    // while this model is a defer script. On a fast page load the model can
    // therefore start before __COT_APP_DATA_READY__ even exists. Waiting only
    // when that promise is already present races the live /api/cot overlay and
    // leaves the decision header/current actor table on the previous report.
    // Wait explicitly for the runtime COT authority instead.
    const runtimeReady=waitForRuntimeCot();
    const[current,active,live,registry,sentiment,candidates]=await Promise.all([
      fetchJson("worldclass/cot-current-state.json"),fetchJson("worldclass/cot-active-edges.json"),fetchJson("worldclass/live-track-record.json",true),fetchJson("worldclass/cot-edge-registry.json"),fetchJson("worldclass/market-sentiment.json",true),fetchJson("worldclass/cot-threshold-candidates.json",true)
    ]);
    await runtimeReady;
    state.current=overlayRuntimeCurrent(current);state.active=rebuildActive(candidates,active);state.live=live||{};state.registry=registry;state.sentiment=sentiment||{};state.market=selectedMarket();return state;
  }

  function rebuildActive(candidates,fallback){
    if(!candidates?.historical_research_frozen){
      if(!window.__COT_LIVE_API__?.markets)return fallback;
      // Fresh actors cannot be compared against an old, preselected trigger
      // list when the complete frozen candidate profiles failed to load.
      const byMarket={...(fallback?.all_taxonomy_by_market||fallback?.by_market||{})};
      for(const market of ['sp500','nq'])byMarket[market]={active_thresholds:[]};
      return{...fallback,by_market:byMarket,all_taxonomy_by_market:byMarket};
    }
    const allByMarket={};
    for(const source of candidates.candidates||[]){
      const current=actorState(source.series),mag=finite(current?.change_magnitude_percentile);
      if(!current||current.direction!==source.direction||mag===null)continue;
      const crossed=Object.entries(source.threshold_profiles||{}).filter(([threshold])=>Number(threshold)<=mag);
      const selections={};
      for(const horizon of FORWARD){
        const rank=metric=>[EVIDENCE_ORDER[metric.evidence_status]??0,finite(metric.independent_n)>=15?1:0];
        const options=crossed.map(([threshold,metrics])=>({threshold:Number(threshold),metric:metrics.find(m=>m.horizon===horizon)})).filter(x=>x.metric);
        options.sort((a,b)=>rank(b.metric)[0]-rank(a.metric)[0]||rank(b.metric)[1]-rank(a.metric)[1]||b.threshold-a.threshold||(finite(b.metric.independent_n)||0)-(finite(a.metric.independent_n)||0));
        const best=options[0];
        if(best)selections[horizon]={selected_threshold:best.threshold,evidence_status:best.metric.evidence_status,independent_n:best.metric.independent_n,excess_vs_baseline_pp:best.metric.excess_vs_baseline_pp};
      }
      const first=selections['1w']||Object.values(selections)[0];
      if(!first)continue;
      const row={...source,actor_label:current.actor_label,actor_role:current.actor_role,current_change_percentile:mag,current_position_percentile:current.position_percentile,current_delta_net_contracts:current.delta_net_contracts,current_delta_net_oi_pp:current.delta_net_oi_pp,selected_threshold:first.selected_threshold,horizon_selections:selections,metrics:source.threshold_profiles[String(first.selected_threshold)],evidence_status:first.evidence_status};
      (allByMarket[source.market]||=( {active_thresholds:[]} )).active_thresholds.push(row);
    }
    const selected=state.current?.presentation_selection?.financial_report;
    const byMarket=Object.fromEntries(Object.entries(allByMarket).map(([market,block])=>[market,{...block,active_thresholds:block.active_thresholds.filter(r=>!selected||!['tff','legacy'].includes(r.dataset)||r.dataset===selected)}]));
    return{...fallback,by_market:byMarket,all_taxonomy_by_market:allByMarket,runtime_current_selection:true};
  }
  function edgeGrade(metric){return metric?evidenceGrade(evidenceStatus(null,metric)):null}
  function liveForecast(market=state.market,horizon="1w",family="combined"){
    const model=matchingLivePredictions(market,family).at(-1)||null;
    if(!model)return null;
    const expected=finite(model[`expected_${horizon}_return_pct`]??model[`expected_${horizon}_return`]??model?.historical_horizons?.[horizon]?.expected_return_pct);
    const probability=finite(model[`probability_positive_${horizon}`]??model[`probability_positive_${horizon}_pct`]??model?.historical_horizons?.[horizon]?.probability_positive);
    if(expected===null&&probability===null)return null;
    return{model,expected,probability,confidence:model.confidence||model?.historical_horizons?.[horizon]?.confidence||"n/a"};
  }

  window.__COT_CURRENT_EDGE_MODEL__={MARKETS,MARKET_ORDER,ROLE_ORDER,ROLE_LABEL,EVIDENCE_ORDER,EVIDENCE_LABEL,VALIDATED_CLASSES,FORWARD,state,finite,currentRows,allActorStates,actorState,selectionFor,profileFor,effectiveRow,activeRows,metricFor,evidenceStatus,evidenceGrade,edgeGrade,liveForecast,sampleLabel,rankedEdges,edgeDirection,edgeExplanation,modelTone,corePrediction,actorLivePredictions,reportDates,directionalRead,summary,bestForwardMetric,marketOpportunities,thresholdWatchlist,macroSnapshot,factorSentiment,sentimentSnapshot,layerAlignment,selectedMarket,rebuildActive,load};
})();
