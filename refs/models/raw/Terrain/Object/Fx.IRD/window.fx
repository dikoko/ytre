// texture
texture Tex0
<
	string UIName = "Base Texture";
	string UIType = "Bitmap";
>;

texture Tex1
<
	string UIName = "Sky Texture";
	string UIType = "Bitmap";
>;

float4 I_a = { 0.7f, 0.7f, 0.7f, 1.0f };    // ambient
float4 I_d = { 1.0f, 1.0f, 1.0f, 1.0f };    // diffuse

float4   vecDLightDir		: GTFX_DLIGHT_DIR	  = {0.0f,-1.0f, 0.0f, 0.f};	// 방향
float4   clrDLightDiffuse	: GTFX_DLIGHT_DIFFUSE = {1.0f, 1.0f, 1.0f, 1.f};	// Diffuse
float4   clrDLightAmbient	: GTFX_DLIGHT_AMBIENT = {1.0f, 1.0f, 1.0f, 1.f};	// Ambient

float4   clrFogColor		: GTFX_FOG_COLOR = {1.0f, 1.0f, 1.0f, 1.0f};	// 색
float    fFogStart			: GTFX_FOG_START = 300.0f;	// 시작 거리
float    fFogEnd			: GTFX_FOG_END   = 400.0f;	// 끝 거리


float4 vScale  = {0.5f, -0.5f, 1.0f, 1.0f};
float4 vOffset = {0.5f,  0.5f, 0.0f, 0.0f};

// transforms
float4x4 View : VIEW; 
float4x4 WorldView : WORLDVIEW; 
float4x4 WorldViewProj  : WORLDVIEWPROJECTION; 

struct VSTEXTURE_OUTPUT
{
    float4 Position : POSITION;
    float2 TexCoord : TEXCOORD0;
    float4 Diffuse : COLOR0;
};

VSTEXTURE_OUTPUT VSWindow
    (
    float4 Position : POSITION, 
    float3 Normal   : NORMAL,
    float2 TexCoord : TEXCOORD0
    )
{
    VSTEXTURE_OUTPUT Out = (VSTEXTURE_OUTPUT)0;
    
    Out.Position  = mul(Position, WorldViewProj);
    Out.TexCoord = TexCoord;

	float3 P = mul(Position, (float4x3)WorldView);
	float3 V = -normalize(P);
	float3 N = normalize(mul(Normal, (float3x3)WorldView));
	float3 L = normalize(mul(-vecDLightDir, (float3x3)View));
    float3 R = normalize(2 * dot(N, L) * N - L);
    Out.Diffuse = I_a * clrDLightAmbient + I_d * clrDLightDiffuse * max(0, dot(N, L)); // diffuse + ambient
    
    float frac = max(P.z, -P.z);
    frac = (frac - fFogStart) / (fFogEnd - fFogStart);
    frac = min(max(frac, 0.0f), 1.0f);
    Out.Diffuse.a = 1.0f - frac;
    
    return Out;    
}

VSTEXTURE_OUTPUT VSSky
    (
    float4 Position : POSITION, 
    float3 Normal   : NORMAL,
    float2 TexCoord : TEXCOORD0
    )
{
    VSTEXTURE_OUTPUT Out = (VSTEXTURE_OUTPUT)0;

	float4 Offset = float4(Normal * 0.01f, 0.0f);
    float4 Pos = mul(Position + Offset, WorldViewProj);
    Out.Position = Pos;
    
	Pos /= Pos.w;
    Pos = Pos * vScale + vOffset;
    Out.TexCoord = Pos;

	float3 P = mul(Position, (float4x3)WorldView);
	float3 V = -normalize(P);
	float3 N = normalize(mul(Normal, (float3x3)WorldView));
	float3 L = normalize(mul(-vecDLightDir, (float3x3)View));
    float3 R = normalize(2 * dot(N, L) * N - L);
    Out.Diffuse = I_a * clrDLightAmbient + I_d * clrDLightDiffuse * max(0, dot(N, L)); // diffuse + ambient    
   
    float frac = max(P.z, -P.z);
    frac = (frac - fFogStart) / (fFogEnd - fFogStart);
    frac = min(max(frac, 0.0f), 1.0f);
    Out.Diffuse.a = (1.0f - frac) * 0.5f ;

    return Out;    
}


technique TestTech
{
    pass BasePass
    {   
        VertexShader = compile vs_1_1 VSWindow();
        PixelShader  = NULL;
        
        // texture
        Texture[0] = (Tex0);
        
        // sampler states
        MinFilter[0] = LINEAR;
        MagFilter[0] = LINEAR;
        MipFilter[0] = POINT;
        
        AlphaBlendEnable = True;
        SrcBlend = SrcAlpha;
        DestBlend = InvSrcAlpha; 

        // set up texture stage states for single texture modulated by diffuse 
        ColorOp[0]   = MODULATE;
        ColorArg1[0] = TEXTURE;
        ColorArg2[0] = DIFFUSE;
        AlphaOp[0]   = SELECTARG1;
        AlphaArg1[0] = DIFFUSE;
        ColorOp[1]   = DISABLE;
        AlphaOp[1]   = DISABLE;
    }
    
    pass SkyPass
    {   
        VertexShader = compile vs_1_1 VSSky();
        PixelShader  = NULL;
        
        // texture
        Texture[0] = (Tex1);
        
        AlphaBlendEnable = True;
        SrcBlend = SrcAlpha;
        DestBlend = InvSrcAlpha;
        
        // sampler states
        MinFilter[0] = LINEAR;
        MagFilter[0] = LINEAR;
        MipFilter[0] = POINT;

        // set up texture stage states for single texture modulated by diffuse 
        ColorOp[0]   = MODULATE;
        ColorArg1[0] = TEXTURE;
        ColorArg2[0] = DIFFUSE;
        AlphaOp[0]   = SELECTARG1;
        AlphaArg1[0] = DIFFUSE;
        ColorOp[1]   = DISABLE;
        AlphaOp[1]   = DISABLE;
    }
}
