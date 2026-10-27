/* Run: node tools/audit_rice_supply.cjs .  (no additional packages required) */
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const dir=path.resolve(process.argv[2]||'.');
const context={document:{addEventListener(){}}};
vm.createContext(context);
for(const file of ['rice-tooltips.js','rice-interpretations.js','rice-supply.js','rice-guidance.js','rice-outlook.js']){
 vm.runInContext(fs.readFileSync(path.join(dir,file),'utf8'),context,{filename:file});
}
const expect=(condition,label)=>{if(!condition)throw Error('FAILED '+label);};
const approx=(actual,expected,label)=>expect(Math.abs(actual-expected)<1e-7,label+': '+actual+' versus '+expected);
let count=0;const ok=(condition,label)=>{expect(condition,label);count++};
const candidate=vm.runInContext('riceNumericCandidate',context);
const conform=vm.runInContext('riceValueConforms',context);
const field=(min,max,step)=>({getAttribute:x=>({min,max,step}[x])});
for(const [value,negative,valid] of [['4.14',false,true],['-2.5',true,true],['-2',false,false],['1e3',false,false],['1.2.3',false,false],['abc',false,false],['+1',true,false]]){
 ok(candidate(value,negative)===valid,'numeric entry '+value);
}
ok(conform('17',field('0.01','60','0.1')),'17 MMT valid despite nonzero minimum');
ok(!conform('17.05',field('0.01','60','0.1')),'reject nonincrement decimal');
ok(!conform('-1',field('0','30','0.1')),'reject negative stocks');
ok(conform('-0.5',field('-5','10','0.1')),'negative growth permitted');
const r=context.calculateRiceOutlook({yieldChange:5,areaChange:0,milling:63,demand:17,openingStocks:2,reserve:2,otherUses:0.5,exports:0});
approx(r.palay,20.6535,'palay production');
approx(r.milled,13.011705,'milled rice');
approx(r.coverage,13.011705/17*100,'production coverage');
approx(r.balance,-4.488295,'supply balance');
approx(r.need,4.488295,'additional supply');
approx(r.required,17/(4.75*.63),'demand-equivalent yield');count+=6;
const interpretation=context.riceInterpretSupply({year:2027,coverage:r.coverage,balance:r.balance,need:r.need,openingStocks:2,reserve:2});
ok(interpretation.includes('For 2027')&&interpretation.includes('76.5%')&&interpretation.includes('4.49 MMT'),'scenario interpretation uses numeric year and calculated figures');
ok(fs.readFileSync(path.join(dir,'rice-outlook.js'),'utf8').includes('const year=Number('),'selected year converted before interpretation');
const sufficient=context.calculateRiceOutlook({yieldChange:100,areaChange:0,milling:63,demand:10,openingStocks:1,reserve:0,otherUses:0,exports:0});
ok(sufficient.need===0,'nonnegative balance yields no shortage');
const food=context.riceGuidedMath({year:2027,demandGrowth:1,yieldChange:0,areaChange:0,recovery:63});
approx(food.food,15.2*1.01**5,'compound food needs');
approx(food.production,19.67*.63,'scenario domestic rice');
approx(food.gap,food.food-food.production,'food-only production gap');count+=3;
const h=[context.riceSupplyPanel(),context.riceGuidancePanel(),context.riceOutlookPanel(),context.riceGuidedScenarioPanel()].join(' ');
for(const term of ['19.67','78.1%','2022','riceScenarioYield','riceOutlookDemand','riceGuideYear'])ok(h.includes(term),'UI value or input '+term);
console.log('PASS: '+count+' rice supply audit assertions (form validation, calculations, source labels and scenario structure)');
