// FUNCIONES REGISTER
function mostrarOnChange() {
     console.log("hola")
             sel = document.getElementById("estado_civil");
             divC = document.getElementById("datcon");
     
             if (sel.value=="Casado") {
                 console.log(sel);
                  divC.style.display = '';
             }
             else {
                  divC.style.display='none';
       
             }
       }
       
 function No_Inquilinos() {
 console.log("hola estoy en la funcion inquilinos")
      sel_inq = document.getElementById("sel_inquilinos");
      div_inq1 = document.getElementById("inq_1");
      div_inq2 = document.getElementById("inq_2");
      div_inq3 = document.getElementById("inq_3");
      div_inq4 = document.getElementById("inq_4");
      div_inq5 = document.getElementById("inq_5");
 
      if (sel_inq.value=="1") 
      {
           console.log(sel_inq.value);
           div_inq1.style.display = '';
      }
      else {
           div_inq1.style.display = 'none';
 
      }
      
      if (sel_inq.value=="2") 
      {
           console.log(sel_inq.value);
           div_inq1.style.display = '';
           div_inq2.style.display = '';
      }
      else {
           div_inq2.style.display = 'none';
 
      }
      
      if (sel_inq.value=="3") 
      {
           console.log(sel_inq.value);
           div_inq1.style.display = '';
           div_inq2.style.display = '';
           div_inq3.style.display = '';
      }
      else {
           div_inq3.style.display = 'none';
 
      }
      
      if (sel_inq.value=="4") 
      {
           console.log(sel_inq.value);
           div_inq1.style.display = '';
           div_inq2.style.display = '';
           div_inq3.style.display = '';
           div_inq4.style.display = '';
      }
      else {
           div_inq4.style.display = 'none';
 
      }
      if (sel_inq.value=="5") 
      {
           console.log(sel_inq.value);
           div_inq1.style.display = '';
           div_inq2.style.display = '';
           div_inq3.style.display = '';
           div_inq4.style.display = '';
           div_inq5.style.display = '';
      }
      else {
           div_inq5.style.display = 'none';
 
      }
 }    
      function toggle(radio) {
        
      
          var div1 = document.getElementById("FS");
          var div2 = document.getElementById("OSPF");
          var div3 = document.getElementById("OSPM");

          var divd1 = document.getElementById("FSD")
      //   console.log(radio.value)
        console.log(radio.id)
       
           if(radio.id=="fiador_obligado1") {
                div1.style.display='';
                divd1.style.display='';
               
            }
            else{
                div1.style.display='none'
                divd1.style.display='none'
                 
                 }
           if(radio.id=="fiador_obligado2"){
           
           div2.style.display='';
          
           }else
           {
                div2.style.display='none';
           }  
           if(radio.id=="fiador_obligado3"){
           
                div3.style.display='';
               
                }else
                {
                     div3.style.display='none';
                }  
           }
 
           // FUNCIONES VW
 function mostrar() {
      console.log("Cargue al inicio soy mostrar 2")
     //  conyu = document.getElementById("conyu");
     //  conyu_v = document.getElementById("n_conyuge");
     //  if(conyu_v.value=="None None None") {
     //      conyu.style.display='none';
     //  }
     //  else{
     //      conyu.style.display='';
     //       }
      
      
      console.log("FN POI")
       var poi2 = document.getElementById("poi2");
       var poi3 = document.getElementById("poi3");
       var poi4 = document.getElementById("poi4");
       var poi5 = document.getElementById("poi5");
  
       var inq2 = document.getElementById("inq2");
       var inq3 = document.getElementById("inq3");
       var inq4 = document.getElementById("inq4");
       var inq5 = document.getElementById("inq5");
       
  
        if(poi2.value=="None") {
             inq2.style.display='none';
         }
         else{
             inq2.style.display='';
              }
       if(poi3.value=="None") {
             inq3.style.display='none';
         }
         else{
             inq3.style.display='';
              }
       if(poi4.value=="None") {
             inq4.style.display='none';
         }
         else{
             inq4.style.display='';
              }
       if(poi5.value=="None") {
             inq5.style.display='none';
         }
         else{
             inq5.style.display='';
              }
              
        console.log("acta")
        var trigger = document.getElementById("fom");
        var div1 = document.getElementById("acta_con");
        var div2 = document.getElementById("datos_empleo");
      
        console.log(trigger.value)
         if(trigger.value=="Persona Fisica") {
              div2.style.display='';
          }
          else{
               div2.style.display='none';
                }
          
        if(trigger.value=="Persona Moral") {
              div1.style.display='';
          }
          else{
               div1.style.display='none';
                }
         }       
            
                   
        
 
 
 
 // FUNCIONES EDIT
 function mostrarEPF() {
      console.log("Cargue al inicio soy mostrarEPF ")
       var poi2 = document.getElementById("n_ocupara_inmueble2");
       var poi3 = document.getElementById("n_ocupara_inmueble3");
       var poi4 = document.getElementById("n_ocupara_inmueble4");
       var poi5 = document.getElementById("n_ocupara_inmueble5");
  
       var inq2 = document.getElementById("inq_2");
       var inq3 = document.getElementById("inq_3");
       var inq4 = document.getElementById("inq_4");
       var inq5 = document.getElementById("inq_5");
       
  
        if(poi2.value=="None") {
             inq2.style.display='none';
         }
         else{
             inq2.style.display='';
              }
       if(poi3.value=="None") {
             inq3.style.display='none';
         }
         else{
             inq3.style.display='';
              }
       if(poi4.value=="None") {
             inq4.style.display='none';
         }
         else{
             inq4.style.display='';
              }
       if(poi5.value=="None") {
             inq5.style.display='none';
         }
         else{
             inq5.style.display='';
              }
  
              console.log("Soy la segunda funcionalidad")
              var mos = document.getElementById("FO");
              var div1 = document.getElementById("FS");
              var div2 = document.getElementById("OSPF");
              var div3 = document.getElementById("OSPM");
              
      
               if(mos.value=="Fiador Solidario") {
                    
                    div1.style.display='';
                   
                }
                else{
                    div1.style.display='none'
                    var div1 = document.getElementById("FS").getElementsByTagName('*');
                    for (var node of div1) {
                         node.disabled = true;
                     }
                     
                     }
               if(mos.value=="Obligado Solidario Persona Fisica"){
               
               div2.style.display='';
              
               }else
               {
                div2.style.display = 'none';
                var div2 = document.getElementById("OSPF").getElementsByTagName('*');
                    for (var node of div2) {
                         node.disabled = true;
                     }
               }  
               if(mos.value=="Obligado Solidario Persona Moral"){
               
                    div3.style.display='';
                   
                    }else
                    {
                        div3.style.display='none';
                        var div3 = document.getElementById("OSPM").getElementsByTagName('*');
                         for (var node of div3) {
                              node.disabled = true;
                          }
                    }  

               
              
                    console.log("hola conyugue")
                    sel = document.getElementById("estado_civil");
                    divC = document.getElementById("datcon");
            
                    if (sel.value=="Casado") {
                        console.log(sel);
                         divC.style.display = '';
                    }
                    else {
                         divC.style.display='none';
              
                    }
              }
              
        
 
  function obligado(){
      var mos = document.getElementById("FO");
      var div1 = document.getElementById("FS");
      var div2 = document.getElementById("OSPF");
      var div3 = document.getElementById("OSPM");
 
    
       if(mos.value=="Fiador Solidario") {
            div1.style.display='';
           
        }
        else{
            div1.style.display='none'
             
             }
       if(mos.value=="Obligado Solidario Persona Fisica"){
       
       div2.style.display='';
      
       }else
       {
            div2.style.display='none';
       }  
       if(mos.value=="Obligado Solidario Persona Moral"){
       
            div3.style.display='';
           
            }else
            {
                 div3.style.display='none';
            }  
       }
         
 