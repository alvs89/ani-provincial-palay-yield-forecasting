/* Transparent, rule-based interpretations for all three rice calculators. */
const riceN=(x,d=2)=>Number(x).toFixed(d);
function riceInterpretProductivity({yieldValue,required,coverage,gap}){
 if(![yieldValue,required,coverage,gap].every(Number.isFinite))return 'Enter valid assumptions to display an interpretation.';
 const difference=Math.abs(required-yieldValue);
 const finding=coverage<100 ? `Domestic production would cover ${riceN(coverage,1)}% of the entered rice requirement, leaving a production-only gap of ${riceN(gap)} MMT. The assumed yield is ${riceN(difference)} MT/ha below the calculated required yield.` : coverage>100 ? `Domestic production would cover ${riceN(coverage,1)}% of the entered rice requirement. The assumed yield exceeds the demand-equivalent required yield by ${riceN(difference)} MT/ha.` : 'Domestic production would exactly cover the assumed annual rice requirement before other supply-account adjustments.';
 return finding+' This is a scenario, not a national forecast. Inventories and other rice uses are excluded; a production gap is not an import requirement.';
}
function riceInterpretFood({year,coverage,gap,food,production}){
 if(![year,coverage,gap,food,production].every(Number.isFinite))return 'Enter valid assumptions to display an interpretation.';
 const status=production<food ? `For ${year}, the assumed domestic output would cover ${riceN(coverage,1)}% of estimated food needs, leaving a food-only production gap of ${riceN(gap)} MMT.` : production>food ? `For ${year}, the assumed domestic output would cover ${riceN(coverage,1)}% of estimated food needs, exceeding them by ${riceN(production-food)} MMT.` : `For ${year}, assumed domestic output would exactly cover estimated food needs.`;
 return status+' Future demand and production use assumptions, not validated forecasts. This does not determine imports because stocks, other uses, seasonality and policy are excluded.';
}
/* Render the variable values as emphasized text without parsing user input as HTML. */
function riceRenderFoodInterpretation(element,{year,coverage,gap,food,production}){
 if(!element)return;
 const numbers=[year,coverage,gap,food,production];
 if(!numbers.every(Number.isFinite)){
  element.textContent='Enter valid assumptions to display an interpretation.';
  return;
 }
 element.replaceChildren();
 const write=text=>element.appendChild(document.createTextNode(text));
 const bold=value=>{const node=document.createElement('strong');node.textContent=String(value);element.appendChild(node)};
 write('For ');bold(year);write(', the assumed domestic output would cover ');bold(riceN(coverage,1)+'%');write(' of estimated food needs');
 if(production<food){write(', leaving a food-only production gap of ');bold(riceN(gap)+' MMT');write('.')}
 else if(production>food){write(', exceeding them by ');bold(riceN(production-food)+' MMT');write('.')}
 else {write(' exactly.')}
 write(' Future demand and production use assumptions, not validated forecasts. This does not determine imports because stocks, other uses, seasonality and policy are excluded.');
}
function riceInterpretSupply({year,coverage,balance,need,openingStocks,reserve}){
 if(![year,coverage,balance,need,openingStocks,reserve].every(Number.isFinite))return 'Enter valid assumptions to display an interpretation.';
 const production=`domestic production would cover ${riceN(coverage,1)}% of the entered annual requirement.`;
 const supply=balance<0 ? `After the entered stock, export, loss and reserve assumptions, the balance would be a deficit of ${riceN(need)} MMT, indicating possible additional supply needs.` : balance>0 ? `After the entered assumptions, the balance would be a surplus of ${riceN(balance)} MMT.` : 'After the entered assumptions, the supply balance would be zero.';
 return `For ${year}, ${production} ${supply} This is not an import recommendation or validated annual prediction. Stock figures are user assumptions, and year selection alone does not forecast production.`;
}

/* Emphasize calculated values, not surrounding explanatory language. */
function riceRenderInterpretation(element, message){
 if(!element)return;
 element.replaceChildren();
 const pattern=/\b\d{4}\b|(?<![\w.])-?\d+(?:\.\d+)?(?:%|\sMMT|\sMT\/ha)?/g;
 let cursor=0;
 for(const match of message.matchAll(pattern)){
  if(match.index>cursor)element.appendChild(document.createTextNode(message.slice(cursor,match.index)));
  const bold=document.createElement('strong');bold.textContent=match[0];element.appendChild(bold);
  cursor=match.index+match[0].length;
 }
 if(cursor<message.length)element.appendChild(document.createTextNode(message.slice(cursor)));
}
