from rest_framework.decorators import api_view
from rest_framework.response import Response
from ....home.models import *
from ...serializers import *
from rest_framework import status
from ....accounts.models import CustomUser
User = CustomUser

@api_view(['GET'])
def inquilinos_list_all(request):
    """
    List all code snippets, or create a new snippet.
    """
    user_session = request.user
    try:    
        if request.method == 'GET':
            if user_session.is_staff:
                snippets = Inquilino.objects.all()
                # Crear una copia de los datos serializados
                serializer = InquilinoSerializers(snippets, many=True)
                serialized_data = serializer.data

                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['is_staff'] = True

                # Devolver la respuesta
                return Response(serialized_data)
            
            elif user_session.rol == "Inmobiliaria":  
                #tengo que busca a los inquilinos que tiene a un agente vinculado
                print("soy inmobiliaria", user_session.name_inmobiliaria)
                agentes = User.objects.all().filter(pertenece_a = user_session.name_inmobiliaria) 
                
                #busqueda de inquilino propios y registrados por mis agentes
                inquilinos_a_cargo = Inquilino.objects.filter(user_id__in = agentes)
                inquilinos_mios = Inquilino.objects.filter(user_id = user_session)
                print("mis registros propios como inmobiliaria",inquilinos_mios)
                mios = inquilinos_a_cargo.union(inquilinos_mios)
                
                #busqueda de inquilino vinculado
                pertenece2 = Inquilino.objects.filter(mi_agente_es__icontains = agentes.values("first_name"))
                pertenece = Inquilino.objects.filter(mi_agente_es__in = agentes.values("first_name"))
                pertenece = pertenece.union(pertenece2)
                
                inquilinos_all = mios.union(pertenece)
                #print("inquilinos a cargo", inquilinos_a_cargo.values())
                print("Registrados por mi o por un agente directo", mios)
                print("Independientes vinculado(s) a un agente(s)", pertenece)
                print("inquilinos_all",inquilinos_all)
                
                
                serializer = InquilinoSerializers(inquilinos_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'1'})
                
                # Agregar el campo 'is_staff'
                for item in serialized_data:
                    item['inmobiliaria'] = True
                    
                return Response(serialized_data)      
            
            elif user_session.rol == "Agente":  
                print("soy Agente", user_session.first_name)
                #obtengo mis inquilinos
                inquilinos_ag = Inquilino.objects.filter(user_id = user_session)
                #obtengo mis inquilinos vinculados
                pertenece = Inquilino.objects.filter(mi_agente_es__icontains = user_session.first_name)
                # pertenece = Inquilino.objects.filter(mi_agente_es = user_session.first_name)
                # pertenece = Inquilino.objects.filter(mi_agente_es__in = user_session.first_name)
                # pertenece = pertenece.union(pertenece2)
                inquilinos_all = inquilinos_ag.union(pertenece)
                serializer = InquilinoSerializers(inquilinos_all, many=True)
                serialized_data = serializer.data
                
                if not serialized_data:
                    print("no hay datos mi carnal")
                    return Response({"message": "No hay datos disponibles",'asunto' :'2'})

                for item in serialized_data:
                    item['agente'] = True
                    
                return Response(serialized_data)         
            
            else:
                # Listar muchos a muchos
                # Obtener todos los inquilinos del usuario actual
                inquilinos_propios = Inquilino.objects.all().filter(user_id = user_session)
                print(inquilinos_propios)
                
                # Obtener todos los arrendadores amigos del usuario actual
                arrendadores_amigos = Arrendador.objects.all().filter(user_id = user_session)
                print(arrendadores_amigos)
                # Obtener inquilinos ligados a los arrendadores amigos
                inquilinos_amigos = Inquilino.objects.filter(amigo_inquilino__receiver__in = arrendadores_amigos)
                print(inquilinos_amigos)
                # Combinar inquilinos propios e inquilinos amigos sin duplicados basados en el ID
                snippets = inquilinos_propios.union(inquilinos_amigos)
                print(snippets)
                
                serializer = InquilinoSerializers(snippets, many=True)
        
                return Response(serializer.data)
    except Exception as e:
        return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
