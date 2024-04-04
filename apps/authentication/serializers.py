from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.conf import settings

from ..accounts.models import CustomUser
User = CustomUser

class UserTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username','email','first_name')

class CustomUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'password','first_name','is_staff')
    
    def create(self,validated_data):
        user = User(**validated_data)
        print("user de en el registro",user)
        user.set_password(validated_data['password'])
        user.save()
        print('usuario salvado en el metodo create del serializar custom')
        return user
            

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = '__all__'
    
    def create(self,validated_data):
        user = User(**validated_data)
        user.set_password(validated_data['password'])
        user.save()
        return user

class UpdateUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('username', 'email', 'name', 'last_name')

class PasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, min_length=6, write_only=True)
    password2 = serializers.CharField(max_length=128, min_length=6, write_only=True)

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError(
                {'password':'Debe ingresar ambas contraseñas iguales'}
            )
        return data

class UserListSerializer(serializers.ModelSerializer):
    class Meta:
        model = User

    def to_representation(self, instance):
        return {
            'id': instance['id'],
            'name': instance['name'],
            'username': instance['username'],
            'email': instance['email']
        }
    
class User2Serializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username','is_staff','rol','first_name')
        
class User2Inmobiliaria(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id','username', 'rol','name_inmobiliaria','pertenece_a')

