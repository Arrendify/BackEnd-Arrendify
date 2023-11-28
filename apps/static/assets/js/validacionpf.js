function validateForm(event) {
    // código de validación
    console.log("hola");
    var form = document.getElementById("Formu");
    var name = document.getElementById("nombre");
    var ap =document.getElementById("apellido");
    var am = document.getElementById("apellido1");
    var ntmpf = document.getElementById("numeroTel");
    var email1 = form.elements.email.value;
    
    // Datos domiciliarios

    var calle = document.getElementById("calle");
    var mun_alc = document.getElementById("municipio_alcaldia");
    var col = document.getElementById("colonia");
    var estado = document.getElementById("estado");
    var num_ext = document.getElementById("num_ext");
    var cp = document.getElementById("codigopostal");
    
    // Datos De Empleo
    var profesion = document.getElementById("profesion");
    var antiguedad = document.getElementById("antiguedad");
    var puesto = document.getElementById("puesto");
    var nte = document.getElementById("numeroTel_empresa");
    var im = document.getElementById("ingreso_men");
    var ne = document.getElementById("nombre_empresa");
    var ee = document.getElementById("email_empresa");
    var c_em = document.getElementById("calle_em");
    var col_em = document.getElementById("colonia_em");
    var ne_em = document.getElementById("num_ext_em");
    var ni_em = document.getElementById("num_int_em");
    var ciudad_em = document.getElementById("ciudad_em");
    var cp_em = document.getElementById("codigo_postal_em");
    var jefe = document.getElementById("jefe");
    var puesto_jefe = document.getElementById("puesto_jefe");
    var pw = document.getElementById("pagina_web");
    var pw_f = document.getElementById("pagina_web_f");

    //Referencia del Arrendatario Anterior
    var n_aa = document.getElementById("nombre_aa")
    var mr_aa = document.getElementById("monto_renta_aa")
    var tel_aa = document.getElementById("telefono_aa")
    var mot = document.getElementById("motivo")
    var dom_ia = document.getElementById("dom_inmueble_arrendado")
    
    // Referencias Personales
    var n_ref1 = document.getElementById("n_ref1")
    var p_ref1 = document.getElementById("p_ref1")
    var tel_ref1 = document.getElementById("tel_ref1")
    var n_ref2 = document.getElementById("n_ref2")
    var p_ref2 = document.getElementById("p_ref2")
    var tel_ref2 = document.getElementById("tel_ref2")
    var n_ref3 = document.getElementById("n_ref3")
    var p_ref3 = document.getElementById("p_ref3")
    var tel_ref3 = document.getElementById("tel_ref3")
    //inquilinos
    var sel_inq = document.getElementById("sel_inquilinos")
    var noi1= document.getElementById("n_ocupara_inmueble1")
    var poi1 = document.getElementById("p_ocupara_inmueble1")
    

    if(name.value==""){
        event.preventDefault();
        name.setAttribute("style", "border-color:red;");
        name.scrollIntoView();   
    }
    
    if (ap.value==""){
        event.preventDefault();
        ap.setAttribute("style", "border-color:red;");
        ap.scrollIntoView();
    }
    
    if (am.value==""){
        event.preventDefault();
        am.setAttribute("style", "border-color:red;");
        am.scrollIntoView();
    }
    
    if (ntmpf.value==""){
        event.preventDefault();
        ntmpf.setAttribute("style", "border-color:red;");
        ntmpf.scrollIntoView();
    }
    if (email1 === "" || !/^\w+([\.-]?\w+)*@\w+([\.-]?\w+)*(\.\w{2,3})+$/.test(email1)) {
        event.preventDefault();
        var email = document.getElementById("email");
        email.setAttribute("style", "border-color:red;");
        email.scrollIntoView();
        // Mostrar un mensaje de error
    }

    if (calle.value==""){
        event.preventDefault();
        calle.setAttribute("style", "border-color:red;");
        calle.scrollIntoView();
    }

    if (mun_alc.value==""){
        event.preventDefault();
        mun_alc.setAttribute("style", "border-color:red;");
        mun_alc.scrollIntoView();
    }

    if (col.value==""){
        event.preventDefault();
        col.setAttribute("style", "border-color:red;");
        col.scrollIntoView();
    }

    if (estado.value==""){
        event.preventDefault();
        estado.setAttribute("style", "border-color:red;");
        estado.scrollIntoView();
    }

    if (num_ext.value==""){
        event.preventDefault();
        num_ext.setAttribute("style", "border-color:red;");
        num_ext.scrollIntoView();
    }

    if (cp.value==""){
        event.preventDefault();
        cp.setAttribute("style", "border-color:red;");
        cp.scrollIntoView();
    }
    // empleo
    if (profesion.value==""){
        event.preventDefault();
        profesion.setAttribute("style", "border-color:red;");
        profesion.scrollIntoView();
    }

    if (puesto.value==""){
        event.preventDefault();
        puesto.setAttribute("style", "border-color:red;");
        puesto.scrollIntoView();
    }

    if (antiguedad.value==""){
        event.preventDefault();
        antiguedad.setAttribute("style", "border-color:red;");
        antiguedad.scrollIntoView();
    }

    if (nte.value==""){
        event.preventDefault();
        nte.setAttribute("style", "border-color:red;");
        nte.scrollIntoView();
    }

    if (im.value==""){
        event.preventDefault();
        im.setAttribute("style", "border-color:red;");
        im.scrollIntoView();
    }

    if (ne.value==""){
        event.preventDefault();
        ne.setAttribute("style", "border-color:red;");
        ne.scrollIntoView();
    }

    if (ee.value==""){
        event.preventDefault();
        ee.setAttribute("style", "border-color:red;");
        ee.scrollIntoView();
    }

    if (c_em.value==""){
        event.preventDefault();
        c_em.setAttribute("style", "border-color:red;");
        c_em.scrollIntoView();
    }

    if (col_em.value==""){
        event.preventDefault();
        col_em.setAttribute("style", "border-color:red;");
        col_em.scrollIntoView();
    }

    if (ne_em.value==""){
        event.preventDefault();
        ne_em.setAttribute("style", "border-color:red;");
        ne_em.scrollIntoView();
    }

    if (ni_em.value==""){
        event.preventDefault();
        ni_em.setAttribute("style", "border-color:red;");
        ni_em.scrollIntoView();
    }

    if (ciudad_em.value==""){
        event.preventDefault();
        ciudad_em.setAttribute("style", "border-color:red;");
        ciudad_em.scrollIntoView();
    }

    if (cp_em.value==""){
        event.preventDefault();
        cp_em.setAttribute("style", "border-color:red;");
        cp_em.scrollIntoView();
    }

    if (jefe.value==""){
        event.preventDefault();
        jefe.setAttribute("style", "border-color:red;");
        jefe.scrollIntoView();
    }

    if (puesto_jefe.value==""){
        event.preventDefault();
        puesto_jefe.setAttribute("style", "border-color:red;");
        puesto_jefe.scrollIntoView();
    }

    if (pw.value==""){
        event.preventDefault();
        pw.setAttribute("style", "border-color:red;");
        pw.scrollIntoView();
    }
    else{
        pw.setAttribute("style", "border-color:green;");
    }

    if (pw_f.value==""){
        event.preventDefault();
        pw.setAttribute("style", "border-color:red;");
        pw.scrollIntoView();
    }
    //Referencia del Arrendatario Anterior
    if (n_aa.value==""){
        event.preventDefault();
        n_aa.setAttribute("style", "border-color:red;");
        n_aa.scrollIntoView();
    }
    if (mr_aa.value==""){
        event.preventDefault();
        mr_aa.setAttribute("style", "border-color:red;");
        mr_aa.scrollIntoView();
    }
    if (tel_aa.value==""){
        event.preventDefault();
        tel_aa.setAttribute("style", "border-color:red;");
        tel_aa.scrollIntoView();
    }
    if (mot.value==""){
        event.preventDefault();
        mot.setAttribute("style", "border-color:red;");
        mot.scrollIntoView();
    }
    if (dom_ia.value==""){
        event.preventDefault();
        dom_ia.setAttribute("style", "border-color:red;");
        dom_ia.scrollIntoView();
    }
    // Referencias Personales
    if (n_ref1.value==""){
        event.preventDefault();
        n_ref1.setAttribute("style", "border-color:red;");
        n_ref1.scrollIntoView();
    }
    if (p_ref1.value==""){
        event.preventDefault();
        p_ref1.setAttribute("style", "border-color:red;");
        p_ref1.scrollIntoView();
    }
    if (tel_ref1.value==""){
        event.preventDefault();
        tel_ref1.setAttribute("style", "border-color:red;");
        tel_ref1.scrollIntoView();
    }
    if (n_ref2.value==""){
        event.preventDefault();
        n_ref2.setAttribute("style", "border-color:red;");
        n_ref2.scrollIntoView();
    }
    if (p_ref2.value==""){
        event.preventDefault();
        p_ref2.setAttribute("style", "border-color:red;");
        p_ref2.scrollIntoView();
    }
    if (tel_ref2.value==""){
        event.preventDefault();
        tel_ref2.setAttribute("style", "border-color:red;");
        tel_ref2.scrollIntoView();
    }
    if (n_ref3.value==""){
        event.preventDefault();
        n_ref3.setAttribute("style", "border-color:red;");
        n_ref3.scrollIntoView();
    }
    if (p_ref3.value==""){
        event.preventDefault();
        p_ref3.setAttribute("style", "border-color:red;");
        p_ref3.scrollIntoView();
    }
    if (tel_ref3.value==""){
        event.preventDefault();
        tel_ref3.setAttribute("style", "border-color:red;");
        tel_ref3.scrollIntoView();
    }
    // inquilinos
    if (sel_inq.value=="Número De Inquilinos"){
        event.preventDefault();
        window.alert("No has selecionado la cantidad de inquilinos") 
        sel_inq.setAttribute("style", "border-color:red;");
        sel_inq.scrollIntoView();
    }
    if (noi1.value==""){
        event.preventDefault();
        noi1.scrollIntoView();
    }
    if (poi1.value==""){
        event.preventDefault();
        poi1.scrollIntoView();
    }


    form.addEventListener("submit", validateForm);
}

