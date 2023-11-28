function sumar()
{
var total = 0;
var total2 = 0;
var total3 = 0;
var valor1 = document.getElementById("val1").value;
if (valor1<10000)
{
    total = 2800;
    var reg = /\d{1,3}(?=(\d{3})+$)/g;



    var Display = document.getElementById("Display");
    var Display2 = document.getElementById("Display2");
    var Display3 = document.getElementById("Display3");
    Display.innerHTML =  (total + '').replace(reg,'$&,');
    Display2.innerHTML = (total + '').replace(reg,'$&,');
    Display3.innerHTML = (total + '').replace(reg,'$&,');
    if (!valor1)
    {
        console.log('esta vacio')
        Display.innerHTML = 0;
        Display2.innerHTML = 0;
        Display3.innerHTML = 0;

    } 
}
else
{
  
    total = (valor1 * 0.28);
    total2 = (valor1 * 0.35);
    total3 = (valor1 * 0.70);
    var dec = total.toFixed()
    var dec2 = total2.toFixed()
    var dec3 = total3.toFixed()
    var reg = /\d{1,3}(?=(\d{3})+$)/g;

    var Display = document.getElementById("Display");
    var Display2 = document.getElementById("Display2");
    var Display3 = document.getElementById("Display3");
    Display.innerHTML =  (dec + '').replace(reg,'$&,');
    Display2.innerHTML = (dec2 + '').replace(reg,'$&,');
    Display3.innerHTML = (dec3 + '').replace(reg,'$&,');
    
    
}
}



// (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
//     (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
//     m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
//     })(window,document,'script','https://www.google-analytics.com/analytics.js','ga');
// ga('create', 'UA-1656750-34', 'auto');
// ga('require', 'linkid', 'linkid.js');
// ga('require', 'displayfeatures');
// ga('send', 'pageview');
                                     
