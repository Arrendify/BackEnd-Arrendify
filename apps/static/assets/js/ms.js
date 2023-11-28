var next_click=document.querySelectorAll(".next_button");
var main_form=document.querySelectorAll(".main");
var step_list = document.querySelectorAll(".progress-bar li");
var num = document.querySelector(".step-number");
let formnumber=0;
var em1 = false;
var em2 = false;
var em3 = false;

next_click.forEach(function(next_click_form){
    next_click_form.addEventListener('click',function(){
        if(!validateform()){
            if (!em1){
                document.getElementById("msj_email").innerText="email invalido";
            }
            return false
        }
        if (em1==true){
            formnumber++;
            updateform();
            progress_forward();
            contentchange();
        }
        else{
            
        }
       
    });
}); 

var back_click=document.querySelectorAll(".back_button");
back_click.forEach(function(back_click_form){
    back_click_form.addEventListener('click',function(){
       formnumber--;
       updateform();
       progress_backward();
       contentchange();
    });
});

var username=document.querySelector("#user_name");
var shownname=document.querySelector(".shown_name");
 

var submit_click=document.querySelectorAll(".submit_button");
submit_click.forEach(function(submit_click_form){
    submit_click_form.addEventListener('click',function(){
       shownname.innerHTML= username.value;
       formnumber++;
       updateform(); 
    });
});

var heart=document.querySelector(".fa-heart");
heart.addEventListener('click',function(){
   heart.classList.toggle('heart');
});


var share=document.querySelector(".fa-share-alt");
share.addEventListener('click',function(){
   share.classList.toggle('share');
});

 

function updateform(){
    main_form.forEach(function(mainform_number){
        mainform_number.classList.remove('active');
    })
    main_form[formnumber].classList.add('active');
} 
 
function progress_forward(){
    // step_list.forEach(list => {
        
    //     list.classList.remove('active');
         
    // }); 
    
     
    num.innerHTML = formnumber+1;
    step_list[formnumber].classList.add('active');
}  

function progress_backward(){
    var form_num = formnumber+1;
    step_list[form_num].classList.remove('active');
    num.innerHTML = form_num;
} 
 
var step_num_content=document.querySelectorAll(".step-number-content");

 function contentchange(){
     step_num_content.forEach(function(content){
        content.classList.remove('active'); 
        content.classList.add('d-none');
     }); 
     step_num_content[formnumber].classList.add('active');
 } 
 
 
function validateform(){
    validate=true;
    var validate_inputs=document.querySelectorAll(".main.active input");
    console.log("validaciones",validate_inputs)
    console.log("email",validate_inputs[9])
    validate_inputs.forEach(function(vaildate_input){
        
        vaildate_input.classList.remove('warning');
        if(vaildate_input.hasAttribute('require')){
            if(vaildate_input.value.length==0){
                validate=false;
                vaildate_input.classList.add('warning');
            }
        else{
            vaildate_input.classList.remove('warning')
        }
        
            
        }
    });
    return validate;
    
}

function validarEmail(input) {
    // Expresión regular para validar el formato del correo electrónico
    var patron = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}$/;

    // Verificar si el valor del campo coincide con el patrón
    if (patron.test(input.value)) {
        if (input.id=="email"){ em1 = true;}
        var val= document.getElementById("msj_email");
        val.innerText="email valido"
        val.style.color="green"
        document.getElementById("email").style.borderColor="green";

    } else {
      // Limpiar mensaje de error
      document.getElementById("msj_email").innerText=""
    }
  }