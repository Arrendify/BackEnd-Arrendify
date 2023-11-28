from rest_framework.decorators import api_view
from rest_framework.response import Response
from ....home.models import *
from ...serializers import *

@api_view(['GET'])
def inquilinos_list_all(request):
    """
    List all code snippets, or create a new snippet.
    """
    user_session = request.user
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
