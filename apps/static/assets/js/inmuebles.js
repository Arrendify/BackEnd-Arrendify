var boton = document.getElementById("finalizar1");
     document.getElementById("step7").onload=block();
     function block (){
         boton.disabled = true
         boton.style.backgroundColor="rgba(0,117,255,0.32)";
     }

    function validar()
    {
        console.log("que onda locos")
        let val_img = document.getElementById("imagenes");

        if  (val_img.value){
            boton.disabled = false
            boton.style.backgroundColor="#0075ff";


        }
    }

    function fin()
    {
        localStorage.removeItem('datos');
    }
        /*function alert0(arren){
            console.log("soy el arrendador",arren)
            Swal.fire({
                title: '¿Éstas seguro?',
                text: "No podrás revertir esta acción",
                icon: 'warning',
                reverseButtons: true,
                showCancelButton: true,
                confirmButtonColor: '#3085d6',
                cancelButtonColor: '#d33',
                confirmButtonText: 'Si, elimina esto',
                cancelButtonText: 'Cancelar'
            }).then((result) => {
            if (result.isConfirmed) {
                setTimeout(function(){
                    console.log("Hola Mundo");
                    window.location.href ="/removerin/{{inmueble.id}}"+arren
                }, 1500);
                Swal.fire({
                        icon: 'success',
                        title: '¡Inmueble Eliminado!',
                        text: 'Se ha elimando de forma exitosa.',
                        showConfirmButton: false,
                        timer: 1500
                    })}
        })}*/
    
        $(function () {
            $("form").keypress(function (e) {
                var key;
                if (window.event)
                    key = window.event.keyCode; //IE
                else
                    key = e.which; //firefox     
                return (key != 13);
            });
        });
    // variables globales    
const arr ={};
document.getElementById("carga_plantar").onload = plantar();
//document.getElementById("carga_pfom").onload = inquilinos()
//document.getElementById("carga_aa").onload = fecha()



function recopilar()
{
// Obtener y Guardar el valor del input en localStorage
console.log("estoy en guardar",JSON.stringify(arr))
localStorage.setItem('datos', JSON.stringify(arr));
}

function plantar()
{
    const storedData = JSON.parse(localStorage.getItem('datos'));
    var k1 = Object.getOwnPropertyNames(storedData);
    console.log("soy k1",k1)
    for(let i= 0; i<k1.length;i++)
    {
        let k2 = document.getElementsByName(k1[i]);
        k2[0].value =  storedData[k1[i]];
        //console.log("soy k2",k2[0]);
    }
}

function prueba2(val){
    console.log(val.name)
    arr[""+val.name] = '' +val.value
    arr2 = val.name;
    let k2 = document.getElementById(arr2);
    console.log("soy k2",k2)
    k2.style.borderColor="green"
    k2.classList.remove('warning')
}
