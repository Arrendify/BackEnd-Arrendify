def Contacto(request):
    contenido_html = (
                """
               <html>
                <head>
                    <style>
                    /* Estilos CSS para el mensaje */
                    body {
                        font-family: Arial, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background-color: #f2f2f2;
                    }

                    .container {
                        max-width: 600px;
                        margin: 0 auto;
                        background-color: #fff;
                        padding: 20px;
                        border-radius: 5px;
                        box-shadow: 0 2px 5px rgba(0, 0, 0, 0.1);
                    }

                    h1 {
                        color: #333;
                        font-size: 24px;
                        margin-bottom: 20px;
                    }

                    p {
                        color: #555;
                        font-size: 16px;
                        line-height: 1.5;
                        margin-bottom: 10px;
                    }

                    /* Estilo para resaltar el párrafo del mensaje */
                    .mensaje {
                        background-color: #f7f7f7;
                        border: 1px solid #ddd;
                        padding: 10px;
                        margin: 10px 0;
                        border-radius: 5px;
                    }
                    </style>
                </head>
                    <body>
                        <div class="container">
                        <img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="logo_arrendify" align="right" style="width: 200px; height: auto;">
                        <br>
                        <br>
                        """
                        
                        f'<h1>Llego una petición de contacto por parte de la persona {request.data.get("nombre")}</h1>'
                        '<h3>Datos del solicitante</h3>'
                        + '<ul>'
                        + f'<li> Nombre: {request.data.get("nombre")}</li>'
                        + f'<li> Email: {request.data.get("email")}</li>'
                        + f'<li> Número de Celular: {request.data.get("numero_celular")}</li>'
                        + '</ul>'
                        
                        """
                        <p>Con el siguiente mensaje: </p>
                        """
                        
                        f'<p class="mensaje">{request.data.get("mensaje")}</p>'
                        """
                        <br>
                        <p>En base a su solicitud usted podra verificar si procede o no a darle un seguimiento </p>
                        <br>
                        """
                        
                        
                        """
                        <hr style="color: #0056b2;" />
                        <table>
                        <tbody><tr>
                            <td align="center" bgcolor="#efefef" style="padding:0;Margin:0;background-color:#efefef;background-image:url(https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png);background-repeat:no-repeat;background-position:left top" background="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/15921614697745363.png">
                            <table class="es-footer-body" align="center" cellpadding="0" cellspacing="0" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;background-color:transparent;width:600px">
                            <tbody><tr>
                                <td align="left" style="padding:0;Margin:0;padding-top:20px;padding-left:20px;padding-right:20px"><!--[if mso]><table style="width:560px" cellpadding="0" 
                                        cellspacing="0"><tr><td style="width:245px" valign="top"><![endif]-->
                                <table cellpadding="0" cellspacing="0" class="es-left" align="left" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:left">
                                <tbody><tr>
                                    <td class="es-m-p20b" align="left" style="padding:0;Margin:0;width:245px">
                                    <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                    <tbody><tr>
                                        <td align="left" class="es-m-txt-c" style="padding:0;Margin:0;font-size:0px"><a target="_blank" href="https://arrendify.com" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img src="https://arrendify.com/wp-content/uploads/2021/02/logo-arrendafy.png" alt="" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic" height="50" width="200"></a></td>
                                    </tr>
                                    <tr>
                                        <td align="left" style="padding:0;Margin:0;padding-top:10px;padding-bottom:10px"><p style="Margin:0;-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;line-height:21px;color:#333333;font-size:14px">Lo hacemos con pasión o no lo hacemos.</p></td>
                                    </tr>
                                    </tbody></table></td>
                                </tr>
                                </tbody>
                                </table>
                                <table cellpadding="0" cellspacing="0" class="es-right" align="right" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px;float:right">
                                <tbody><tr>
                                    <td align="left" style="padding:0;Margin:0;width:295px">
                                    <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                    <tbody><tr>
                                        <td align="left" style="padding:0;Margin:0;padding-top:20px"><h3 style="Margin:0;line-height:24px;mso-line-height-rule:exactly;font-family:arial, 'helvetica neue', helvetica, sans-serif;font-size:20px;font-style:normal;font-weight:bold;color:#333333">Contacto</h3></td>
                                    </tr>
                                    <tr>
                                        <td style="padding:0;Margin:0">
                                        <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                        <tbody><tr class="links-images-left">
                                            <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:10px;padding-bottom:7px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/39781614763048410.png" alt="30 Commercial Road Fratton, Australia" title="30 Commercial Road Fratton, Australia" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle"> Blvrd Manuel Ávila Camacho 80, Int 204, El Parque, 53398 Naucalpan de Juárez, MEX</a></td>
                                        </tr>
                                        </tbody></table></td>
                                    </tr>
                                    <tr>
                                        <td style="padding:0;Margin:0">
                                        <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                        <tbody><tr class="links-images-left">
                                            <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:7px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/95711614763048218.png" alt="1-888-452-1505" title="1-888-452-1505" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">(55) 7258 9136</a></td>
                                        </tr>
                                        </tbody></table></td>
                                    </tr>
                                    <tr>
                                        <td style="padding:0;Margin:0">
                                        <table cellpadding="0" cellspacing="0" width="100%" class="es-menu" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                        <tbody><tr class="links-images-left">
                                            <td align="left" valign="top" width="100%" id="esd-menu-id-0" style="Margin:0;padding-left:5px;padding-right:5px;padding-top:7px;padding-bottom:10px;border:0"><a " href="#" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:none;display:block;color:#666666;font-size:14px"><img src="https://tlr.stripocdn.email/content/guids/CABINET_2bacaf58048cb1918f88ffe5b8979b28/images/97961614763048410.png" alt="Mon - Sat: 8am - 5pm, Sunday: CLOSED" title="Mon - Sat: 8am - 5pm, Sunday: CLOSED" align="absmiddle" width="20" style="display:inline-block !important;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic;padding-right:5px;vertical-align:middle">Lun - Sab: 8:30am - 6pm, Domingo: Cerrado</a></td>
                                        </tr>
                                        </tbody></table></td>
                                    </tr>
                                    </tbody></table></td>
                                </tr>
                                </tbody></table><!--[if mso]></td></tr></table><![endif]--></td>
                            </tr>
                            <tr>
                                <td align="left" style="padding:20px;Margin:0">
                                <table cellpadding="0" cellspacing="0" width="100%" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                <tbody><tr>
                                    <td align="center" valign="top" style="padding:0;Margin:0;width:560px">
                                    <table cellpadding="0" cellspacing="0" width="100%" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                    <tbody><tr>
                                        <td align="center" style="padding:0;Margin:0;font-size:0">
                                        <table cellpadding="0" cellspacing="0" class="es-table-not-adapt es-social" role="presentation" style="mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;border-spacing:0px">
                                        <tbody><tr>
                                            <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.facebook.com/Arrendify-110472377752254" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Facebook" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/facebook-logo-black.png" alt="Fb" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                            <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://twitter.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Twitter" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/twitter-logo-black.png" alt="Tw" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                            <td align="center" valign="top" style="padding:0;Margin:0;padding-right:25px"><a target="_blank" href="https://www.instagram.com/Arrendify/" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Instagram" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/instagram-logo-black.png" alt="Inst" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                            <td align="center" valign="top" style="padding:0;Margin:0"><a target="_blank" href="https://www.youtube.com/channel/UCSUDtH0ybV9O-AnZHjI-_Xg" style="-webkit-text-size-adjust:none;-ms-text-size-adjust:none;mso-line-height-rule:exactly;text-decoration:underline;color:#666666;font-size:14px"><img title="Youtube" src="https://tlr.stripocdn.email/content/assets/img/social-icons/logo-black/youtube-logo-black.png" alt="Yt" width="32" style="display:block;border:0;outline:none;text-decoration:none;-ms-interpolation-mode:bicubic"></a></td>
                                        </tr>
                                        </tbody></table></td>
                                    </tr>
                                    </tbody></table></td>
                                </tr>
                                </tbody></table></td>
                            </tr>
                            </tbody></table></td>
                        </tr>
                        </tbody>
                        </table>
                        
                        <br>
                        <!-- <img src="apps/static/assets/media/img/logo-arrendafy.png" alt="logo_arrendify" style="width: 200px; height: auto;"> -->
                        </div>
                    </body>
                </html>
                 """)
    return contenido_html